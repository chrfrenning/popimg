import os
import time
import shortuuid
from flask import Flask, Response, redirect, request, render_template

app = Flask(__name__)

images = {}
events = []

@app.route('/events')
def sse():
    def generate():
        while True:
            if events:
                event = events.pop(0)
                yield f"data: {event}\n\n"
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')

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
        'data': request.data
        }
    events.append(short_id)
    return {'location': f'/{short_id}'}, 201

@app.route('/<short_id>', methods=['DELETE'])
def delete_image(short_id):
    # check if the image exists
    if short_id not in images:
        return '', 404
    # delete the image
    del images[short_id]
    return '', 204

@app.route('/', methods=['GET'])
def home():
    # create a short id
    short_id = shortuuid.ShortUUID().random(length=5)
    # redirect the user to /short_id
    return redirect(f'/{short_id}')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)