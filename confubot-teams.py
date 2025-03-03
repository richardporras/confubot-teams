import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Flask app is running on Azure!"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Azure proporciona el puerto dinámico
    app.run(host="0.0.0.0", port=port, debug=True)
