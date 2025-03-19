import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';

// Configure axios defaults
axios.defaults.baseURL = 'http://localhost:5001';
axios.defaults.headers.post['Content-Type'] = 'application/json';
axios.defaults.withCredentials = true;

const API_BASE_URL = 'http://localhost:5001/api';

function App() {
  const [prompt, setPrompt] = useState('');
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState('');
  const [error, setError] = useState('');
  const [spotifyToken, setSpotifyToken] = useState(null);
  const [playlistInfo, setPlaylistInfo] = useState(null);

  // Check for existing token in localStorage on component mount
  useEffect(() => {
    const token = localStorage.getItem('spotifyToken');
    if (token) {
      setSpotifyToken(token);
    }
  }, []);

  const onDrop = useCallback(acceptedFiles => {
    const file = acceptedFiles[0];
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

  const handleSpotifyLogin = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/login`);
      window.location.href = response.data.auth_url;
    } catch (error) {
      setError('Failed to initiate Spotify login. Please try again.');
      console.error('Login error:', error);
    }
  };

  const handleSpotifyCallback = async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    
    if (code) {
      try {
        const response = await axios.get(`${API_BASE_URL}/callback?code=${code}`);
        const token = response.data.access_token;
        setSpotifyToken(token);
        localStorage.setItem('spotifyToken', token); // Store token in localStorage
        window.location.href = '/'; // Redirect back to main page
      } catch (error) {
        setError('Failed to complete Spotify login. Please try again.');
        console.error('Callback error:', error);
      }
    }
  };

  const getRecommendations = async () => {
    if (!prompt.trim()) {
      setError('Please enter a prompt');
      return;
    }

    setLoading(true);
    setError('');
    setLoadingStep('Analyzing your input...');

    try {
      const response = await axios.post(`${API_BASE_URL}/recommend`, {
        text_prompt: prompt,
        user_token: spotifyToken // Include Spotify token if available
      });

      setRecommendations(response.data.recommendations);
      if (response.data.playlist) {
        setPlaylistInfo(response.data.playlist);
      }
    } catch (error) {
      console.error('Recommendation error:', error);
      if (error.response?.status === 401) {
        setError('Your Spotify session has expired. Please reconnect with Spotify.');
        setSpotifyToken(null);
        localStorage.removeItem('spotifyToken');
      } else {
        setError(error.response?.data?.error || 'Failed to get recommendations. Please try again.');
      }
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
      const response = await axios.post(`${API_BASE_URL}/recommend`, {
        image: base64Data,
        user_token: spotifyToken // Include Spotify token if available
      });

      setRecommendations(response.data.recommendations);
      if (response.data.playlist) {
        setPlaylistInfo(response.data.playlist);
      }
    } catch (error) {
      console.error('Image analysis error:', error);
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

  // Handle Spotify callback when component mounts
  useEffect(() => {
    if (window.location.pathname === '/callback') {
      handleSpotifyCallback();
    }
  }, []);

  return (
    <div className="min-h-screen bg-gray-100 py-6 flex flex-col justify-center sm:py-12">
      <div className="relative py-3 sm:max-w-xl sm:mx-auto">
        <div className="relative px-4 py-10 bg-white shadow-lg sm:rounded-3xl sm:p-20">
          <div className="max-w-md mx-auto">
            <div className="divide-y divide-gray-200">
              <div className="py-8 text-base leading-6 space-y-4 text-gray-700 sm:text-lg sm:leading-7">
                <h1 className="text-3xl font-bold text-center mb-8">AI Playlist Generator</h1>
                
                {!spotifyToken && (
                  <div className="text-center mb-8">
                    <button
                      onClick={handleSpotifyLogin}
                      className="bg-green-500 text-white px-6 py-2 rounded-full hover:bg-green-600 transition-colors"
                    >
                      Connect with Spotify
                    </button>
                  </div>
                )}

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      How are you feeling?
                    </label>
                    <input
                      type="text"
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder="e.g., I'm feeling energetic and want to work out"
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                      disabled={loading}
                    />
                  </div>

                  <div {...getRootProps()} className={`mt-4 p-6 border-2 border-dashed rounded-lg text-center cursor-pointer transition-colors ${isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-500'}`}>
                    <input {...getInputProps()} disabled={loading} />
                    {isDragActive ? (
                      <p>Drop the image here...</p>
                    ) : (
                      <p>Drag and drop an image here, or click to select one</p>
                    )}
                  </div>

                  <button
                    onClick={getRecommendations}
                    disabled={loading || !prompt.trim()}
                    className={`w-full py-2 px-4 rounded-md text-white font-medium ${
                      loading || !prompt.trim()
                        ? 'bg-gray-400 cursor-not-allowed'
                        : 'bg-indigo-600 hover:bg-indigo-700'
                    }`}
                  >
                    {loading ? 'Generating...' : 'Get Recommendations'}
                  </button>
                </div>

                {loading && (
                  <div className="mt-4 text-center text-gray-600">
                    <p>{loadingStep}</p>
                    <p className="text-sm">This may take a few moments...</p>
                  </div>
                )}

                {error && (
                  <div className="mt-4 p-4 bg-red-50 text-red-700 rounded-md">
                    {error}
                  </div>
                )}

                {recommendations.length > 0 && (
                  <div className="mt-8">
                    <h2 className="text-xl font-semibold mb-4">Recommended Tracks</h2>
                    <div className="space-y-4">
                      {recommendations.map((track, index) => (
                        <div key={index} className="p-4 bg-gray-50 rounded-lg">
                          <h3 className="font-medium">{track.name}</h3>
                          <p className="text-sm text-gray-600">{track.artist}</p>
                          <p className="text-sm text-gray-500">{track.album}</p>
                          {track.preview_url && (
                            <audio controls className="mt-2 w-full">
                              <source src={track.preview_url} type="audio/mpeg" />
                              Your browser does not support the audio element.
                            </audio>
                          )}
                          <a
                            href={track.external_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-indigo-600 hover:text-indigo-800 mt-2 inline-block"
                          >
                            Open in Spotify
                          </a>
                        </div>
                      ))}
                    </div>

                    {playlistInfo && (
                      <div className="mt-6 p-4 bg-green-50 rounded-lg">
                        <h3 className="text-lg font-semibold text-green-800">Playlist Created!</h3>
                        <p className="text-green-700">{playlistInfo.playlist_name}</p>
                        <a
                          href={playlistInfo.playlist_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-green-600 hover:text-green-800 mt-2 inline-block"
                        >
                          Open Playlist in Spotify
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App; 