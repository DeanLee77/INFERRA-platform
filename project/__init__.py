from datetime import timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)
db = SQLAlchemy()

def create_app():
    app = Flask(__name__, static_folder=None)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    # app.config['SESSION_TYPE'] = os.getenv('SESSION_TYPE')
    # app.config['SESSION_TYPE'] = 'filesystem'
    # app.permanent_session_lifetime = timedelta(days=365)
    # Initialize app
    db.init_app(app)
    CORS(app)

    # return app
    return app
