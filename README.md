Nawabshah Heat Intelligence 🌡️🔥
A Flask-based machine learning and data-driven web application designed to analyze, visualize, and forecast heat stress and environmental data for Nawabshah, utilizing NASA POWER satellite datasets.

🚀 Features
Interactive Dashboard: Clean web interface built with Flask and HTML/CSS templates (dashboard.html, login.html).   
image_532ebc.png

NASA Climate Data Integration: Processes historical weather and environmental metrics derived from NASA POWER observations (nasa_power_nawabshah.csv).

Heat Risk Analytics: Provides insights and intelligence on temperature trends and neighborhood heat stress to support environmental monitoring.

🛠️ Tech Stack
Backend: Python, Flask, Pandas

Frontend: HTML5, CSS3, Jinja2 Templates

Deployment: PythonAnywhere

📁 Project Structure
Plaintext
nawabshah-heat-intelligence/
│
├── app.py                  # Main Flask application and routing
├── requirements.txt        # Python package dependencies
├── nasa_power_nawabshah.csv# Dataset containing NASA climate/weather logs
└── templates/              # HTML layout templates
    ├── dashboard.html      # Main user dashboard interface
    └── login.html          # User authentication page
⚙️ Local Setup & Installation
Clone the repository:

Bash
git clone https://github.com/aqsa-AliDev/nawabshah-heat-intelligence.git
cd nawabshah-heat-intelligence
Install dependencies:

Bash
pip install -r requirements.txt
Run the application:

Bash
python app.py
