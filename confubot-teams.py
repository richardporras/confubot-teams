import os

from flask import (Flask, redirect, render_template, request,
                   send_from_directory, url_for)

app = Flask(__name__)

@app.route('/')
def index():
   print('Request for index page received')
   return "OK"

@app.route('/ping')
def index():
   print('Request for ping')
   return "Pong"

if __name__ == '__main__':
   app.run()
