import os
import time
import queue
import shortuuid
import redis
import qrcode
import base64
from flask import Flask, Response, redirect, request, render_template, url_for
from flask_cors import CORS
from io import BytesIO
from enum import Enum

app = Flask(__name__)

images = {}
walls = {}
event_clients = []

class Image:
    def __init__(self, id, wall_id, data, content_type):
        self.id = id
        self.wall_id = wall_id
        self.data = data
        self.content_type = content_type
        self.owner_key = shortuuid.uuid()
        self.timestamp = time.time()

class Wall:
    def __init__(self, id):
        self.id = id
        self.owner_key = shortuuid.uuid()
        self.image_ids = [] # ids into the images dictionary

class EventType(Enum):
    ADD = 'add'
    DELETE = 'delete'

class Event:
    def __init__(self, type : EventType, image : Image, wall_id : str):
        self.type = type
        self.image = image
        self.wall_id = wall_id
        self.timestamp = time.time()

    def __str__(self) -> str:
        # create json of type, image.id, image.url
        return f'{{"type": "{self.type.value}", "id": "{self.image.id}", "url": "/i/{self.image.id}?t={self.image.timestamp}"}}'

CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/app')
def get_app_html():
    return render_template('app.html')

@app.route('/events')
def sse():
    # get the wall id from the w query parameter
    wall_id = request.args.get('w')

    def generate():
        q = queue.Queue()
        event_clients.append(q)
        try:
            while True:
                event = q.get()
                if event.wall_id == wall_id:
                    yield f"data: {event}\n\n"
        except GeneratorExit:
            event_clients.remove(q)

    return Response(generate(), mimetype='text/event-stream')

def broadcast_event(event):
    for client in event_clients:
        client.put(event)

@app.route('/w/<wall_id>', methods=['GET'])
def wall(wall_id):
    # check that the wall exists
    wall = walls.get(wall_id, None)
    if wall is None:
        # do we have a key to create the wall?
        if request.args.get('k') is None:
            return redirect(url_for('home'))
        
        # create the wall
        wall = Wall(wall_id)
        wall.owner_key = request.args.get('k')
        walls[wall_id] = wall
    
    # check that the owner key matches
    if request.args.get('k') != wall.owner_key:
        return '', 403

    # Generate QR code for /app URL
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(f"{url_for('get_app_html', _external=True)}?w={wall_id}")
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    qr_code_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    # get the images from the wall
    images_list = [{'id': id, 'url': f'/i/{id}?t={image.timestamp}', 'timestamp': image.timestamp} for id, image in images.items() if image.wall_id == wall_id]
    # sort the images by timestamp desc
    images_list = sorted(images_list, key=lambda x: x['timestamp'], reverse=False)

    # return the wall
    return render_template('wall.html', wall_id=wall_id, images=images_list, qr_code=qr_code_base64, app_url=f"{url_for('get_app_html', _external=True)}?w={wall_id}")

@app.route('/w/<wall_id>', methods=['POST'])
def upload_image(wall_id):
    # Get the wall
    wall = walls.get(wall_id, None)
    if wall is None:
        return '', 404
    # ID for the image
    short_id = shortuuid.uuid()
    # Get the content type
    content_type = request.headers.get('Content-Type')
    # check that the type is a valid image, content type image/*
    if not content_type.startswith('image/'):
        return '', 400
    # Store the image in the images dictionary
    image = Image(short_id, wall_id, request.data, content_type)
    images[short_id] = image
    # Add the image to the wall
    wall.image_ids.append(short_id)
    # Broadcast the event
    broadcast_event(Event(EventType.ADD, image, wall.id))
    return {
        'location': url_for('show_image', id=short_id),
        'owner_key': image.owner_key
        }, 201

@app.route('/i/<id>', methods=['GET'])
def show_image(id):
    # check if the image exists
    image = images.get(id, None)
    if image is None:
        return '', 404
    # return the image
    return image.data, 200, {'Content-Type': image.content_type}

@app.route('/i/<id>', methods=['DELETE'])
def delete_image(short_id):
    # Get the image
    image = images.get(short_id, None)
    if image is None:
        return '', 404
    # get the owner key from the request
    owner_key = request.headers.get('Owner-Key')
    # check that the owner key matches
    if owner_key != image.owner_key:
        return '', 403
    # remove the image from its wall
    wall = walls[image.wall_id]
    wall.image_ids.remove(short_id)
    # delete the image
    del images[short_id]
    # broadcast the event
    broadcast_event(Event(EventType.DELETE, image, wall.id))
    return '', 204

@app.route('/', methods=['GET'])
def home():
    # create a new wall
    wall_id = shortuuid.uuid()
    wall = Wall(wall_id)
    walls[wall_id] = wall
    # redirect to the wall
    return redirect(f"{url_for('wall', wall_id=wall_id)}?k={wall.owner_key}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    
    debug = True
    if os.environ.get('PWD', '') == '/app':
        debug = False
    
    app.run(host='0.0.0.0', port=port, debug=debug)