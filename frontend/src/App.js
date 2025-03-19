import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';

// Configure axios defaults
axios.defaults.baseURL = 'http://localhost:5001';
axios.defaults.headers.post['Content-Type'] = 'application/json';
axios.defaults.withCredentials = true;

// Configure logging
const log = {
  info: (message, data = null) => {
    console.log(`[INFO] ${message}`, data || '');
  },
  error: (message, error = null) => {
    console.error(`[ERROR] ${message}`, error || '');
  },
  debug: (message, data = null) => {
    console.debug(`[DEBUG] ${message}`, data || '');
  }
};

const API_BASE_URL = 'http://localhost:5001/api';

function App() {
  const [textPrompt, setTextPrompt] = useState('');
  const [image, setImage] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [moodDescription, setMoodDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState('');
  const [error, setError] = useState('');
  const [spotifyToken, setSpotifyToken] = useState(null);
  const [createPlaylist, setCreatePlaylist] = useState(false);
  const [playlistUrl, setPlaylistUrl] = useState(null);
  const [creatingPlaylist, setCreatingPlaylist] = useState(false);

  // Check for existing token in localStorage on component mount
  useEffect(() => {
    const token = localStorage.getItem('spotifyToken');
    if (token) {
      log.info('Found existing Spotify token');
      setSpotifyToken(token);
    }
  }, []);

  const onDrop = useCallback(acceptedFiles => {
    const file = acceptedFiles[0];
    log.info('Image file dropped', { filename: file.name, size: file.size });
    const reader = new FileReader();
    reader.onload = () => {
      const base64Data = reader.result.split(',')[1];
      handleImageUpload(base64Data);
    };
    reader.readAsDataURL(file);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpeg', '.jpg', '.png']
    },
    multiple: false
  });

  // Handle Spotify login
  const handleSpotifyLogin = async () => {
    try {
      log.info('Initiating Spotify login');
      const response = await axios.get(`${API_BASE_URL}/login`);
      if (response.data.auth_url) {
        log.info('Redirecting to Spotify auth URL');
        localStorage.setItem('redirectUrl', window.location.href);
        window.location.href = response.data.auth_url;
      }
    } catch (error) {
      log.error('Spotify login failed', error);
      setError('Failed to initiate Spotify login. Please try again.');
    }
  };

  // Handle Spotify callback when component mounts
  useEffect(() => {
    const handleCallback = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const code = urlParams.get('code');
      
      if (code) {
        try {
          log.info('Processing Spotify callback');
          const response = await axios.get(`${API_BASE_URL}/callback?code=${code}`);
          if (response.data.access_token) {
            log.info('Spotify login successful');
            setSpotifyToken(response.data.access_token);
            localStorage.setItem('spotifyToken', response.data.access_token);
            
            const redirectUrl = localStorage.getItem('redirectUrl') || '/';
            localStorage.removeItem('redirectUrl');
            window.location.href = redirectUrl;
          }
        } catch (error) {
          log.error('Spotify callback failed', error);
          setError('Failed to complete Spotify login. Please try again.');
        }
      }
    };

    handleCallback();
  }, []);

  const getRecommendations = async () => {
    if (!textPrompt && !image) {
      log.error('No input provided');
      setError('Please enter text or upload an image');
      return;
    }

    setLoading(true);
    setError('');
    setLoadingStep('Analyzing your input...');

    try {
      const requestData = {};
      
      if (textPrompt) {
        log.info('Processing text prompt', { prompt: textPrompt });
        requestData.text_prompt = textPrompt;
      }
      if (image) {
        log.info('Processing image upload', { filename: image.name });
        const reader = new FileReader();
        reader.onload = async () => {
          const base64Data = reader.result.split(',')[1];
          requestData.image = base64Data;
          
          try {
            log.debug('Sending image analysis request');
            const response = await axios.post(`${API_BASE_URL}/recommend`, requestData);
            log.info('Received recommendations', { count: response.data.recommendations.length });
            setRecommendations(response.data.recommendations);
            setMoodDescription(response.data.mood_description);
            if (response.data.playlist) {
              setPlaylistUrl(response.data.playlist.playlist_url);
            }
          } catch (err) {
            log.error('Image analysis failed', err);
            setError(err.response?.data?.error || 'Failed to get recommendations. Please try again.');
          } finally {
            setLoading(false);
            setLoadingStep('');
          }
        };
        reader.readAsDataURL(image);
        return;
      }
      
      if (spotifyToken) {
        requestData.user_token = spotifyToken;
      }
      if (createPlaylist) {
        requestData.create_playlist = true;
      }

      log.debug('Sending recommendation request', requestData);
      const response = await axios.post(`${API_BASE_URL}/recommend`, requestData);
      log.info('Received recommendations', { count: response.data.recommendations.length });
      setRecommendations(response.data.recommendations);
      setMoodDescription(response.data.mood_description);
      if (response.data.playlist) {
        setPlaylistUrl(response.data.playlist.playlist_url);
      }
    } catch (err) {
      log.error('Recommendation request failed', err);
      setError(err.response?.data?.error || 'Failed to get recommendations. Please try again.');
    } finally {
      setLoading(false);
      setLoadingStep('');
    }
  };

  const handleImageUpload = async (base64Data) => {
    setLoading(true);
    setError('');
    setLoadingStep('Analyzing your image...');

    try {
      log.debug('Sending image analysis request');
      const response = await axios.post(`${API_BASE_URL}/recommend`, {
        image: base64Data,
        user_token: spotifyToken
      });

      log.info('Received recommendations', { count: response.data.recommendations.length });
      setRecommendations(response.data.recommendations);
      if (response.data.playlist) {
        setPlaylistUrl(response.data.playlist.playlist_url);
      }
    } catch (error) {
      log.error('Image analysis failed', error);
      if (error.response?.status === 401) {
        setError('Your Spotify session has expired. Please reconnect with Spotify.');
        setSpotifyToken(null);
        localStorage.removeItem('spotifyToken');
      } else {
        setError(error.response?.data?.error || 'Failed to analyze image. Please try again.');
      }
    } finally {
      setLoading(false);
      setLoadingStep('');
    }
  };

  const handlePlaylistCreation = async () => {
    if (!spotifyToken) {
      log.error('No Spotify token available for playlist creation');
      setError('Please login to Spotify first');
      return;
    }

    setCreatingPlaylist(true);
    setError('');

    try {
      log.info('Creating Spotify playlist');
      const response = await axios.post(`${API_BASE_URL}/recommend`, {
        text_prompt: textPrompt,
        user_token: spotifyToken,
        create_playlist: true
      });

      if (response.data.playlist) {
        log.info('Playlist created successfully', response.data.playlist);
        setPlaylistUrl(response.data.playlist.playlist_url);
      }
    } catch (err) {
      log.error('Playlist creation failed', err);
      setError(err.response?.data?.error || 'Failed to create playlist. Please try again.');
    } finally {
      setCreatingPlaylist(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 to-black text-white p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-8 text-center">AI Music Recommender</h1>
        
        {/* Input Section */}
        <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6 mb-8">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Describe your mood or upload an image</label>
              <textarea
                value={textPrompt}
                onChange={(e) => setTextPrompt(e.target.value)}
                placeholder="I'm feeling energetic and want to work out..."
                className="w-full p-3 rounded-lg bg-white/5 border border-white/10 focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
                rows="3"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Or upload an image</label>
              <div
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  image ? 'border-purple-500 bg-purple-500/10' : 'border-white/20 hover:border-purple-500'
                } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                onClick={() => !loading && document.getElementById('image-upload').click()}
              >
                <input
                  type="file"
                  id="image-upload"
                  accept="image/*"
                  onChange={(e) => setImage(e.target.files[0])}
                  className="hidden"
                  disabled={loading}
                />
                {image ? (
                  <div className="flex items-center justify-center space-x-2">
                    <span className="text-purple-400">✓</span>
                    <span>{image.name}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setImage(null);
                      }}
                      className="text-red-400 hover:text-red-300"
                    >
                      ×
                    </button>
                  </div>
                ) : (
                  <p>Click to upload an image</p>
                )}
              </div>
            </div>

            {/* Spotify Login and Playlist Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                {!spotifyToken ? (
                  <button
                    onClick={handleSpotifyLogin}
                    className="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg transition-colors"
                    disabled={loading}
                  >
                    Login with Spotify
                  </button>
                ) : (
                  <div className="flex items-center space-x-2">
                    <span className="text-green-400">✓</span>
                    <span>Connected to Spotify</span>
                  </div>
                )}
              </div>

              {spotifyToken && (
                <div className="flex items-center space-x-2">
                  <label className="text-sm">Create Playlist</label>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={createPlaylist}
                      onChange={(e) => setCreatePlaylist(e.target.checked)}
                      disabled={loading}
                    />
                    <div className="w-11 h-6 bg-gray-700 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-800 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
                  </label>
                </div>
              )}
            </div>

            <button
              onClick={getRecommendations}
              disabled={loading || (!textPrompt && !image)}
              className={`w-full py-3 rounded-lg font-medium transition-colors ${
                loading || (!textPrompt && !image)
                  ? 'bg-gray-600 cursor-not-allowed'
                  : 'bg-purple-600 hover:bg-purple-700'
              }`}
            >
              {loading ? 'Generating Recommendations...' : 'Get Recommendations'}
            </button>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6 mb-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500 mx-auto mb-4"></div>
            <p className="text-purple-400">{loadingStep}</p>
            <p className="text-sm text-gray-400 mt-2">This may take a few moments...</p>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-8 text-red-400">
            {error}
          </div>
        )}

        {/* Results Section */}
        {recommendations.length > 0 && (
          <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6">
            <h2 className="text-2xl font-bold mb-4">Your Recommendations</h2>
            <p className="text-purple-400 mb-6">{moodDescription}</p>
            
            <div className="space-y-4">
              {recommendations.map((track, index) => (
                <div key={index} className="flex items-center justify-between bg-white/5 rounded-lg p-4">
                  <div>
                    <h3 className="font-medium">{track.name}</h3>
                    <p className="text-sm text-gray-400">{track.artist}</p>
                    <p className="text-xs text-gray-500">{track.album}</p>
                  </div>
                  <div className="flex items-center space-x-4">
                    {track.preview_url && (
                      <audio controls className="h-8">
                        <source src={track.preview_url} type="audio/mpeg" />
                      </audio>
                    )}
                    <a
                      href={track.external_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-purple-400 hover:text-purple-300"
                    >
                      Open in Spotify
                    </a>
                  </div>
                </div>
              ))}
            </div>

            {/* Playlist Creation Section */}
            {!playlistUrl && spotifyToken && (
              <div className="mt-6 text-center">
                <button
                  onClick={handlePlaylistCreation}
                  disabled={creatingPlaylist}
                  className={`inline-block px-6 py-3 rounded-lg transition-colors ${
                    creatingPlaylist
                      ? 'bg-gray-600 cursor-not-allowed'
                      : 'bg-green-500 hover:bg-green-600 text-white'
                  }`}
                >
                  {creatingPlaylist ? 'Creating Playlist...' : 'Create Playlist in Spotify'}
                </button>
              </div>
            )}

            {/* Playlist Link */}
            {playlistUrl && (
              <div className="mt-6 text-center">
                <a
                  href={playlistUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block bg-green-500 hover:bg-green-600 text-white px-6 py-3 rounded-lg transition-colors"
                >
                  Open Playlist in Spotify
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App; 