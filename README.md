# AI Playlist Generator

An AI-powered music playlist generator that creates personalized playlists based on text descriptions or images.

## Features

- Generate music recommendations based on text descriptions
- Create and save playlists directly to Spotify
- Preview tracks before adding them to playlists


## In Process of Implementing
- Analyze images to create mood-based playlists
- Modern, responsive UI with drag-and-drop image upload
- Improving prompting

## Prerequisites

- Python 3.8 or higher
- Node.js 14 or higher
- Spotify Developer Account
- Hugging Face Account

## Setup

1. Clone the repository:
```bash
git clone github.com/kkuang0/playlist_reccomender_system.git
cd playlist_recommender_system
```

2. Set up environment variables:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Update the `.env` file with your credentials:
     - Get Spotify credentials from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
     - Get Hugging Face token from [Hugging Face Settings](https://huggingface.co/settings/tokens)

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Install frontend dependencies:
```bash
cd frontend
npm install
```

## Running the Application

1. Start the Flask backend:
```bash
python app.py
```

2. In a new terminal, start the React frontend:
```bash
cd frontend
npm start
```

3. Open your browser and navigate to `http://localhost:3000`

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Make your changes
4. Submit a pull request


