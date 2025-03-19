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
from huggingface_hub import login, InferenceClient
import logging
import socket
import base64
import random
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
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
    logger.error("Spotify credentials not found in environment variables")
    raise ValueError("Spotify credentials not found. Please check your .env file.")

logger.info("Initializing Spotify client...")
# Initialize Spotify client for app-only operations
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=spotify_client_id,
    client_secret=spotify_client_secret
))

# Initialize Hugging Face client
huggingface_token = os.getenv('HUGGINGFACE_TOKEN')
if not huggingface_token:
    logger.error("Hugging Face token not found in environment variables")
    raise ValueError("Hugging Face token not found. Please check your .env file.")

logger.info("Initializing Hugging Face client...")
login(token=huggingface_token)
hf_client = InferenceClient(token=huggingface_token)

# Initialize Spotify OAuth with additional scopes
logger.info("Initializing Spotify OAuth...")
sp_oauth = SpotifyOAuth(
    client_id=spotify_client_id,
    client_secret=spotify_client_secret,
    redirect_uri=spotify_redirect_uri,
    scope='playlist-modify-public playlist-modify-private user-read-private user-read-email user-read-recently-played user-top-read playlist-read-private playlist-read-collaborative'
)

logger.info("Initializing models...")
# Remove local model initialization since we're using the Inference API
logger.info("Models initialized successfully")

def analyze_text_prompt(prompt, user_role=None):
    """Analyze text prompt using the Llama model"""
    try:
        logger.info(f"Analyzing text prompt: {prompt[:50]}...")
        logger.debug(f"User role: {user_role}")
        
        # Enhanced system prompt with user role context
        system_prompt = """You are a Gen Z Music Vibe Curator. 
        Analyze user statements for emotional tone, energy level, and cultural references. 
        Match these vibes to appropriate music genres and moods.
        Decipher slang and cultural references. 
        Extract keywords and phrases directly from the user's input.
        
        CRITICAL INSTRUCTION: You MUST detect and mention any artists, songs, or albums in the user's input.
        Your response MUST start with "artist: [name]" if an artist is mentioned.
        
        Examples:
        Input: "I like Drake's music"
        Response: "artist: Drake Mood: Hip-hop, R&B, Melodic"
        
        Input: "I love Taylor Swift's songs"
        Response: "artist: Taylor Swift Mood: Pop, Emotional, Storytelling"
        
        Input: "I want something like The Weeknd"
        Response: "artist: The Weeknd Mood: R&B, Dark, Atmospheric"
        
        Format your response concisely and extract the mood, genre, key words and phrases.
        """
        
        # Add user role context if available
        role_context = "Gen Z brainrot music listener."
        if user_role:
            role_context = f"\nUser Role: {user_role}"
        
        # Format prompt for Mistral model
        full_prompt = f"<s>[INST] {system_prompt}{role_context}\n\nInput: {prompt} [/INST]"
        
        logger.debug("Sending request to Hugging Face Inference API")
        # Use Hugging Face Inference API with Mistral model
        raw_response = hf_client.text_generation(
            full_prompt,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_new_tokens=50,
            temperature=0.7,
            top_p=0.95,
            do_sample=True,
            return_full_text=False
        )
        
        # Clean up the response
        response = raw_response.split('\n')[0]  # Take only the first line
        response = response.replace('What kind of music recommendations do you recommend?', '')
        response = response.replace('What kinds of music recommendations do you recommend?', '')
        
        # Extract mentioned song, artist, or album
        mentioned_entity = None
        if 'artist:' in response.lower():
            # Extract the mentioned entity
            parts = response.lower().split('artist:')
            if len(parts) > 1:
                mentioned_entity = parts[1].strip().split()[0]  # Take first word after "artist:"
                # Remove the entity from the mood description
                response = parts[0].strip()
        
        # Limit the response length
        if len(response) > 100:
            response = response[:100] + "..."
            
        logger.info(f"Generated mood description: {response}")
        if mentioned_entity:
            logger.info(f"Detected mentioned entity: {mentioned_entity}")
        
        return {
            'mood_description': response.strip(),
            'raw_response': raw_response,
            'full_prompt': full_prompt,
            'mentioned_entity': mentioned_entity
        }
    except Exception as e:
        logger.error(f"Error in text analysis: {str(e)}", exc_info=True)
        raise

def analyze_image(image_data):
    """Analyze image using Hugging Face Inference API"""
    try:
        logger.info("Processing image analysis request")
        # Convert base64 to image
        image = Image.open(io.BytesIO(image_data))
        
        logger.debug("Sending image to Hugging Face Inference API")
        # Use Hugging Face Inference API for image analysis
        response = hf_client.image_classification(
            image,
            model="microsoft/resnet-50"
        )
        
        # Extract the top prediction
        top_prediction = response[0]
        logger.info(f"Image analysis result: {top_prediction['label']}")
        return f"Image mood: {top_prediction['label']}"
    except Exception as e:
        logger.error(f"Error in image analysis: {str(e)}", exc_info=True)
        raise

def analyze_user_preferences(user_spotify):
    """Analyze user's listening history and playlists to understand their preferences"""
    try:
        logger.info("Analyzing user preferences")
        # Get user's top tracks
        top_tracks = user_spotify.current_user_top_tracks(limit=20, time_range='medium_term')
        top_artists = user_spotify.current_user_top_artists(limit=20, time_range='medium_term')
        
        # Get user's playlists
        user_playlists = user_spotify.current_user_playlists(limit=50)
        
        # Get recently played tracks
        recently_played = user_spotify.current_user_recently_played(limit=20)
        
        # Extract genres and artists
        genres = set()
        artists = set()
        
        # Analyze top artists
        for artist in top_artists['items']:
            genres.update(artist['genres'])
            artists.add(artist['name'])
        
        # Analyze playlists
        for playlist in user_playlists['items']:
            try:
                playlist_tracks = user_spotify.playlist_tracks(playlist['id'])
                for item in playlist_tracks['items']:
                    if item['track']:
                        artists.add(item['track']['artists'][0]['name'])
            except Exception as e:
                logger.warning(f"Could not analyze playlist {playlist['name']}: {str(e)}")
                continue
        
        # Analyze recently played
        for item in recently_played['items']:
            if item['track']:
                artists.add(item['track']['artists'][0]['name'])
        
        logger.info(f"Found {len(genres)} genres and {len(artists)} artists")
        return {
            'genres': list(genres),
            'artists': list(artists),
            'top_tracks': [track['name'] for track in top_tracks['items']]
        }
    except Exception as e:
        logger.error(f"Error analyzing user preferences: {str(e)}", exc_info=True)
        return None

def clean_mood_description_for_spotify(description):
    logger.debug(f"Cleaning mood description: {description}")
    remove_phrases = [
        "Based on the image content:", "captures this mood", "Image mood:", "Mood:",
        "feeling:", "emotion:", "vibe:", "ambiance:", "atmosphere:", "Image:",
    ]
    for phrase in remove_phrases:
        description = description.replace(phrase, "")
    cleaned = " ".join(description.split()).strip()
    logger.debug(f"Cleaned description: {cleaned}")
    return cleaned

def extract_filters(description):
    logger.debug(f"Extracting filters from: {description}")
    genres = ['rock', 'pop', 'jazz', 'classical', 'hip-hop', 'rap', 'edm',
              'electronic', 'folk', 'country', 'blues', 'soul', 'r&b',
              'metal', 'reggae', 'latin', 'indie', 'dance', 'alternative']
    filters = []
    search_terms = []

    words = description.lower().replace('-', ' ').split()
    for word in words:
        if word in genres:
            filters.append(f'genre:{word}')
        elif word.isdigit() and 1900 <= int(word) <= 2100:
            decade = int(word) - (int(word) % 10)
            filters.append(f'year:{decade}-{decade+9}')
        else:
            search_terms.append(word)

    result = ' '.join(search_terms), filters
    logger.debug(f"Extracted filters: {result}")
    return result

def get_spotify_recommendations(mood_description, user_token=None, limit=10, mentioned_entity=None):
    logger.info(f"Getting Spotify recommendations for: {mood_description}")
    if mentioned_entity:
        logger.info(f"Prioritizing recommendations based on mentioned entity: {mentioned_entity}")
    
    cleaned_description = clean_mood_description_for_spotify(mood_description)
    base_terms, filters = extract_filters(cleaned_description)

    if user_token:
        sp = spotipy.Spotify(auth=user_token)
        logger.debug("Using authenticated Spotify client")
    else:
        sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())
        logger.debug("Using app-only Spotify client")

    # Helper function to build track dictionaries
    def build_track(item):
        return {
            'name': item['name'],
            'artist': item['artists'][0]['name'],
            'album': item['album']['name'],
            'preview_url': item['preview_url'],
            'external_url': item['external_urls']['spotify'],
            'popularity': item['popularity']
        }
    
    # Helper function to log track details
    def log_tracks(track_list):
        for track in track_list:
            logger.info(f"Recommended track: {track['name']} by {track['artist']} (Album: {track['album']}, Popularity: {track['popularity']})")

    # If there's a mentioned entity, prioritize it in the search using a combined search query
    if mentioned_entity:
        combined_results = sp.search(q=mentioned_entity, type="artist,track", limit=limit)
        artist_items = combined_results.get('artists', {}).get('items', [])
        if artist_items:
            artist = artist_items[0]
            artist_id = artist['id']
            logger.info(f"Found artist: {artist['name']} (ID: {artist_id})")
            
            # Get artist's top tracks
            artist_top_tracks = sp.artist_top_tracks(artist_id)['tracks']
            tracks = [build_track(item) for item in artist_top_tracks][:limit//2]
            
            try:
                related_artists = sp.artist_related_artists(artist_id)['artists'][:2]
                for related_artist in related_artists:
                    related_tracks = sp.artist_top_tracks(related_artist['id'])['tracks']
                    tracks.extend([build_track(item) for item in related_tracks][:limit//4])
            except Exception as e:
                logger.warning(f"Could not get related artists: {str(e)}")
                more_tracks = sp.artist_top_tracks(artist_id)['tracks'][limit//2:limit]
                tracks.extend([build_track(item) for item in more_tracks])
            
            # Remove duplicates and limit to requested size
            tracks = list({track['name']: track for track in tracks}.values())[:limit]
            logger.info(f"Found {len(tracks)} tracks based on artist and related artists")
            log_tracks(tracks)
            return tracks
        else:
            # If no artist found, try track search from combined results
            track_items = combined_results.get('tracks', {}).get('items', [])
            if track_items:
                tracks = [build_track(item) for item in track_items]
                # Get related tracks from the same artist
                first_artist_id = track_items[0]['artists'][0]['id']
                related_tracks = sp.artist_top_tracks(first_artist_id)['tracks'][:limit//2]
                tracks.extend([build_track(item) for item in related_tracks])
                
                # Remove duplicates and limit to requested size
                tracks = list({track['name']: track for track in tracks}.values())[:limit]
                logger.info(f"Found {len(tracks)} tracks based on mentioned entity")
                log_tracks(tracks)
                return tracks

    # If no mentioned entity or no results found, fall back to mood-based search
    query = ' '.join(filters + base_terms.split())
    logger.debug(f"Using mood-based search query: {query}")
    
    results = sp.search(q=query, type='track', limit=limit)
    logger.info(f"Found {len(results['tracks']['items'])} tracks")
    tracks = []
    for item in results['tracks']['items']:
        track_info = build_track(item)
        tracks.append(track_info)

    if not tracks and filters:
        logger.info("No results with filters, trying without filters")
        results = sp.search(q=base_terms, type='track', limit=limit)
        tracks = [build_track(item) for item in results['tracks']['items']]
        logger.info(f"Found {len(tracks)} tracks without filters")
    
    log_tracks(tracks)
    return tracks

def create_spotify_playlist(user_token, mood_description, tracks):
    if not user_token:
        logger.error("No Spotify token provided for playlist creation")
        raise ValueError("No Spotify token provided")

    logger.info(f"Creating playlist for mood: {mood_description}")
    user_spotify = spotipy.Spotify(auth=user_token)

    user_info = user_spotify.me()
    user_id = user_info['id']
    logger.debug(f"Creating playlist for user: {user_id}")

    clean_description = clean_mood_description_for_spotify(mood_description)

    playlist_name = f"Recommended: {clean_description}"
    playlist_description = f"AI-generated playlist based on: {clean_description}"

    playlist = user_spotify.user_playlist_create(
        user_id,
        name=playlist_name,
        description=playlist_description,
        public=True
    )
    logger.info(f"Created playlist: {playlist_name}")

    track_uris = [track['external_url'].split('/')[-1] for track in tracks]
    user_spotify.playlist_add_items(playlist['id'], track_uris)
    logger.info(f"Added {len(track_uris)} tracks to playlist")

    return {
        'playlist_id': playlist['id'],
        'playlist_url': playlist['external_urls']['spotify'],
        'playlist_name': playlist_name
    }

@app.route('/api/recommend', methods=['POST'])
def recommend():
    """Handle recommendation requests"""
    try:
        data = request.get_json()
        if not data:
            logger.error("No JSON data provided in request")
            return jsonify({'error': 'No JSON data provided'}), 400
            
        logger.info(f"Received recommendation request with data: {data}")
        
        if 'text_prompt' in data:
            # Analyze text prompt with user role if available
            model_response = analyze_text_prompt(
                data['text_prompt'],
                user_role=data.get('user_role')
            )
            mood_description = model_response['mood_description']
            mentioned_entity = model_response.get('mentioned_entity')
        elif 'image' in data:
            # Decode base64 image
            try:
                image_data = base64.b64decode(data['image'])
                mood_description = analyze_image(image_data)
                model_response = None
                mentioned_entity = None
            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                return jsonify({'error': 'Invalid image data'}), 400
        else:
            logger.error("No input provided in request")
            return jsonify({'error': 'No input provided'}), 400
        
        # Get recommendations from Spotify
        recommendations = get_spotify_recommendations(
            mood_description, 
            data.get('user_token'),
            mentioned_entity=mentioned_entity
        )
        
        response_data = {
            'mood_description': mood_description,
            'recommendations': recommendations,
            'model_response': model_response
        }
        
        # Create playlist only if explicitly requested and user token is provided
        if data.get('create_playlist', False) and 'user_token' in data and data['user_token']:
            try:
                playlist_info = create_spotify_playlist(data['user_token'], mood_description, recommendations)
                response_data['playlist'] = playlist_info
            except ValueError as e:
                logger.error(f"Playlist creation error: {str(e)}")
                return jsonify({'error': str(e)}), 401
            except Exception as e:
                logger.error(f"Error creating playlist: {str(e)}", exc_info=True)
                return jsonify({'error': 'Failed to create playlist'}), 500
        
        logger.info("Successfully generated recommendations")
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error in recommend endpoint: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    logger.debug("Health check endpoint called")
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    local_ip = socket.gethostbyname(socket.gethostname())
    logger.info(f"Starting server on {local_ip}:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)
