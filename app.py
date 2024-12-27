from flask import Flask, redirect, request, session, url_for, jsonify
from requests_oauthlib import OAuth2Session
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

# OAuth2 configuratie
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
TOKEN_URL = "https://connect.garmin.com/oauth-service/oauth/token"
AUTHORIZE_URL = "https://connect.garmin.com/oauth-service/oauth/authorize"
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:5000/callback")

@app.route("/")
def index():
    """
    Homepage met link naar OAuth-login.
    """
    if "oauth_token" in session:
        return jsonify({"message": "Je bent al ingelogd", "token": session["oauth_token"]})
    return '<a href="/login">Inloggen met Garmin Connect</a>'

@app.route("/login")
def login():
    """
    Start de OAuth-login en stuur gebruiker door naar Garmin Connect.
    """
    oauth = OAuth2Session(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI)
    authorization_url, state = oauth.authorization_url(AUTHORIZE_URL)
    session["oauth_state"] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    """
    Ontvang de OAuth-callback en sla de token op in de sessie.
    """
    oauth = OAuth2Session(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, state=session["oauth_state"])
    token = oauth.fetch_token(TOKEN_URL, client_secret=CLIENT_SECRET, authorization_response=request.url)
    session["oauth_token"] = token
    return jsonify({"message": "Ingelogd!", "token": token})

@app.route("/logout")
def logout():
    """
    Verwijder de sessie en log uit.
    """
    session.pop("oauth_token", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
