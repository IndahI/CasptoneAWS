# MelanomaScan - Skin Cancer Detection Web Application

MelanomaScan is an advanced web application that combines AI-powered melanoma detection with an intelligent chatbot for skin health information. Built with Flask and modern web technologies, it provides both analysis tools and educational resources about melanoma skin cancer.

## Key Features

### Melanoma Detection
- Upload and analyze skin lesion images
- Local image processing for quick results
- Secure file handling with size and type validation
- Visual result presentation with detailed analysis

### AI Health Assistant
- Powered by Google's Gemini AI
- Natural language interaction in Bahasa Indonesia
- Real-time typing animation for responses
- Markdown formatting support for better readability
- Interactive features (like, dislike, copy responses)

### User Management
- **Registered Users**
  - Unlimited access to all features
  - Secure authentication with password hashing
  - Personalized usage tracking
  
- **Guest Access**
  - Daily limit: 3 image analyses
  - Daily limit: 3 chatbot interactions
  - Automatic counter reset every 24 hours

## Technical Stack

### Backend
- **Framework**: Flask (Python)
- **Database**: SQLite
- **AI Services**: Google Gemini AI
- **Security**: Werkzeug security functions
- **File Handling**: Werkzeug utilities

### Frontend
- **Templating**: Jinja2
- **Styling**: Custom CSS with Bootstrap
- **Icons**: Font Awesome
- **Interactivity**: Vanilla JavaScript
- **Markdown**: marked.js for chat formatting

## Prerequisites

- Python 3.8+
- Google Gemini API key
- Modern web browser
- Internet connection for AI features

## Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/melanoma-scan.git
   cd melanoma-scan
   ```

2. **Set Up Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   Create a `.env` file:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

5. **Initialize Database**
   ```bash
   python app.py
   ```
   The database will be automatically initialized on first run.

## Project Structure

```
melanoma-scan/
├── app.py              # Main application file
├── config.py           # Configuration settings
├── requirements.txt    # Python dependencies
├── static/            
│   ├── css/           # Stylesheets
│   ├── js/            # JavaScript files
│   └── images/        # Static images
├── templates/          # HTML templates
│   ├── layout.html    # Base template
│   ├── login.html     # Authentication pages
│   ├── chatbot.html   # AI chat interface
│   └── ...
├── uploads/           # User uploaded images
└── database.db        # SQLite database
```

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
```

### Guest Usage Table
```sql
CREATE TABLE guest_usage (
    id INTEGER PRIMARY KEY,
    uploads INTEGER DEFAULT 0,
    chatbot_interactions INTEGER DEFAULT 0,
    last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Security Features

- Password hashing with Werkzeug
- Secure file upload validation
- Session-based authentication
- Environment variable protection
- Input sanitization
- CORS protection

## Browser Support

- Chrome (recommended)
- Firefox
- Safari
- Edge

## Usage Limits

### Guest Users
- 3 image analyses per day
- 3 chatbot interactions per day
- Counter resets at midnight

### Registered Users
- Unlimited image analyses
- Unlimited chatbot interactions
- Full feature access

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
