from flask import Flask, request, jsonify, redirect, session
from flask_cors import CORS
import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
from PIL import Image
import io
import torch
from huggingface_hub import login
import logging
import socket
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session management

# Configure CORS - more permissive for development
CORS(app, 
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "OPTIONS"])

# Get Spotify credentials
spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
spotify_redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI', 'http://localhost:3000/callback')

if not spotify_client_id or not spotify_client_secret:
    raise ValueError("Spotify credentials not found. Please check your .env file.")

# Initialize Spotify client for app-only operations
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=spotify_client_id,
    client_secret=spotify_client_secret
))

# Initialize Spotify OAuth
sp_oauth = SpotifyOAuth(
    client_id=spotify_client_id,
    client_secret=spotify_client_secret,
    redirect_uri=spotify_redirect_uri,
    scope='playlist-modify-public playlist-modify-private user-read-private user-read-email'
)

# Login to Hugging Face
huggingface_token = os.getenv('HUGGINGFACE_TOKEN')
if not huggingface_token:
    raise ValueError("Hugging Face token not found. Please check your .env file.")
login(token=huggingface_token)

logger.info("Initializing models...")
# Initialize text analysis model (using a smaller model)
text_model_name = "facebook/opt-125m"  # Using a smaller model
text_tokenizer = AutoTokenizer.from_pretrained(text_model_name)
text_model = AutoModelForCausalLM.from_pretrained(
    text_model_name,
    torch_dtype=torch.float16,
    device_map="auto"
)

# Initialize image analysis model
image_analyzer = pipeline("image-classification", model="microsoft/resnet-50")
logger.info("Models initialized successfully")

def analyze_text_prompt(prompt):
    """Analyze text prompt using OPT model to extract mood and preferences"""
    try:
        system_prompt = "You are a music recommendation expert. Analyze the user's prompt and extract key musical elements, mood, and preferences. Be concise and focus on musical aspects. Limit your response to 2-3 sentences."
        full_prompt = f"{system_prompt}\n\nUser: {prompt}\nAssistant:"
        
        inputs = text_tokenizer(full_prompt, return_tensors="pt").to(text_model.device)
        outputs = text_model.generate(
            **inputs,
            max_new_tokens=50,  # Further reduced token length
            temperature=0.7,
            top_p=0.95,
            do_sample=True,
            pad_token_id=text_tokenizer.eos_token_id,
            num_return_sequences=1,
            early_stopping=True
        )
        
        response = text_tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Extract only the model's response (after "Assistant:")
        response = response.split("Assistant:")[-1].strip()
        
        # Clean up the response
        # Remove any repetitive phrases
        response = response.split('\n')[0]  # Take only the first line
        response = response.replace('What kind of music recommendations do you recommend?', '')
        response = response.replace('What kinds of music recommendations do you recommend?', '')
        response = response.replace('Assistant:', '')
        
        # Limit the response length
        if len(response) > 100:
            response = response[:100] + "..."
            
        return response.strip()
    except Exception as e:
        logger.error(f"Error in text analysis: {str(e)}")
        raise

def analyze_image(image_data):
    """Analyze image using ResNet-50 to extract mood and atmosphere"""
    try:
        # Convert base64 to image
        image = Image.open(io.BytesIO(image_data))
        
        # Get image classification results
        results = image_analyzer(image)
        
        # Extract top 3 most relevant categories
        top_categories = [result['label'] for result in results[:3]]
        
        # Create a prompt for the text model to interpret these categories
        categories_prompt = f"Based on these image categories: {', '.join(top_categories)}, suggest appropriate music mood and style."
        
        # Use the text model to interpret the image categories
        return analyze_text_prompt(categories_prompt)
    except Exception as e:
        logger.error(f"Error in image analysis: {str(e)}")
        raise

def get_spotify_recommendations(mood_description):
    """Get music recommendations from Spotify based on mood description"""
    try:
        # Clean up the mood description for Spotify search
        search_query = mood_description.replace('\n', ' ').strip()
        if len(search_query) > 100:
            search_query = search_query[:100]
            
        logger.info(f"Searching Spotify with query: {search_query}")
        
        # Search for tracks based on mood
        results = spotify.search(q=search_query, type='track', limit=10)
        tracks = results['tracks']['items']
        
        # Extract track information
        recommendations = []
        for track in tracks:
            recommendations.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'album': track['album']['name'],
                'preview_url': track['preview_url'],
                'external_url': track['external_urls']['spotify']
            })
        
        return recommendations
    except Exception as e:
        logger.error(f"Error getting Spotify recommendations: {str(e)}")
        raise

def create_spotify_playlist(user_token, mood_description, tracks):
    """Create a playlist and add tracks to it"""
    try:
        if not user_token:
            raise ValueError("No Spotify token provided")

        # Create a Spotify client with user token
        user_spotify = spotipy.Spotify(auth=user_token)
        
        # Verify token is valid by making a test request
        try:
            user_info = user_spotify.me()
            user_id = user_info['id']
        except Exception as e:
            logger.error(f"Invalid Spotify token: {str(e)}")
            raise ValueError("Invalid or expired Spotify token")
        
        # Create playlist
        playlist_name = f"Recommended: {mood_description}"
        playlist_description = f"AI-generated playlist based on: {mood_description}"
        
        playlist = user_spotify.user_playlist_create(
            user_id,
            name=playlist_name,
            description=playlist_description,
            public=True
        )
        
        # Add tracks to playlist
        track_uris = [track['external_url'].split('/')[-1] for track in tracks]
        user_spotify.playlist_add_items(playlist['id'], track_uris)
        
        return {
            'playlist_id': playlist['id'],
            'playlist_url': playlist['external_urls']['spotify'],
            'playlist_name': playlist_name
        }
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error creating playlist: {str(e)}")
        raise

@app.route('/api/login', methods=['GET'])
def login():
    """Redirect to Spotify login page"""
    auth_url = sp_oauth.get_authorize_url()
    return jsonify({'auth_url': auth_url})

@app.route('/api/callback', methods=['GET'])
def callback():
    """Handle Spotify callback"""
    try:
        code = request.args.get('code')
        token_info = sp_oauth.get_access_token(code)
        
        if 'error' in token_info:
            return jsonify({'error': token_info['error']}), 400
            
        return jsonify({
            'access_token': token_info['access_token'],
            'refresh_token': token_info.get('refresh_token'),
            'expires_in': token_info['expires_in']
        })
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommend', methods=['POST'])
def recommend():
    """Handle recommendation requests"""
    try:
        data = request.json
        logger.info(f"Received request with data: {data}")
        
        if 'text_prompt' in data:
            # Analyze text prompt
            mood_description = analyze_text_prompt(data['text_prompt'])
        elif 'image' in data:
            # Analyze image
            mood_description = analyze_image(data['image'])
        else:
            return jsonify({'error': 'No input provided'}), 400
        
        # Get recommendations from Spotify
        recommendations = get_spotify_recommendations(mood_description)
        
        response_data = {
            'mood_description': mood_description,
            'recommendations': recommendations
        }
        
        # If user token is provided, create playlist
        if 'user_token' in data and data['user_token']:
            try:
                playlist_info = create_spotify_playlist(data['user_token'], mood_description, recommendations)
                response_data['playlist'] = playlist_info
            except ValueError as e:
                return jsonify({'error': str(e)}), 401
            except Exception as e:
                logger.error(f"Error creating playlist: {str(e)}")
                return jsonify({'error': 'Failed to create playlist'}), 500
        
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error in recommend endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Get local IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    logger.info(f"Local IP address: {local_ip}")
    
    # Run the app
    app.run(host='0.0.0.0', port=5001, debug=True) 