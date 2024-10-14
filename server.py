import os
import time
import queue
import shortuuid
from flask import Flask, Response, redirect, request, render_template

app = Flask(__name__)

images = {}
events = []
clients = []

@app.route('/wall')
def wall():
    images_list = [{'short_id': short_id, 'timestamp': image['timestamp']} for short_id, image in images.items()]
    print(images_list)
    # sort the images by timestamp desc
    images_list = sorted(images_list, key=lambda x: x['timestamp'], reverse=True)
    # take only the ids
    images_list = [image['short_id'] for image in images_list]
    return render_template('wall.html', images=images_list)

@app.route('/events')
def sse():
    def generate():
        q = queue.Queue()
        clients.append(q)
        try:
            while True:
                event = q.get()
                yield f"data: {event}\n\n"
        except GeneratorExit:
            clients.remove(q)

    return Response(generate(), mimetype='text/event-stream')

def broadcast_event(event):
    for client in clients:
        client.put(event)

@app.route('/<short_id>', methods=['GET'])
def show_image(short_id):
    # check if the image exists
    has_image = short_id in images
    # return the image
    return render_template('image.html', has_image=has_image, short_id=short_id), 200

@app.route('/<short_id>/image', methods=['GET'])
def show_image_page(short_id):
    # check if the image exists
    if short_id not in images:
        return '', 404
    # get the image
    return images[short_id]['data'], 200, {'Content-Type': images[short_id]['content_type']}

@app.route('/<short_id>', methods=['PUT'])
def upload_image(short_id):
    # Get the content type
    content_type = request.headers.get('Content-Type')
    print(content_type)
    # check that the type is a valid image, content type image/*
    if not content_type.startswith('image/'):
        return '', 400
    # Store the image in the images dictionary
    images[short_id] = {
        'content_type': content_type,
        'data': request.data,
        'timestamp': time.time()
        }
    broadcast_event(short_id)
    return {'location': f'/{short_id}'}, 201

@app.route('/<short_id>', methods=['DELETE'])
def delete_image(short_id):
    # check if the image exists
    if short_id not in images:
        return '', 404
    # delete the image
    del images[short_id]
    return '', 204

@app.route('/', methods=['POST'])
def create_image():
    return upload_image( shortuuid.uuid() )

@app.route('/', methods=['GET'])
def home():
    return redirect(f'/{shortuuid.uuid()}')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    
    debug = True
    if os.environ.get('PWD', '') == '/app':
        debug = False
    
    app.run(host='0.0.0.0', port=port, debug=debug)