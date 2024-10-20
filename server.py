import os
import queue
import qrcode.image.svg
import shortuuid
import qrcode
import qrcode.image.svg
import base64
import tempfile
from datetime import datetime, timezone, timedelta
from flask import Flask, Response, redirect, request, render_template, url_for
from flask_cors import CORS
from io import BytesIO

from config import STRIPE_SIGNING_SECRET, STRIPE_API_KEY, STRIPE_PUBLIC_KEY, STRIPE_PRICE_ID

import stripe
stripe.api_key = STRIPE_API_KEY

from services import EmailService, BlobService
from models import Image, Wall, WallStatus, Event, EventType, User
from datalayers import UserDataLayer, WallDataLayer, ImageDataLayer


DEBUG_MODE = True
if os.environ.get('PWD', '') == '/app':
    DEBUG_MODE = False

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

if DEBUG_MODE == False:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

event_clients = []

# if DEBUG_MODE == False:
#     app.config['PREFERRED_URL_SCHEME'] = 'https'
#     app.config['SERVER_NAME'] = 'livewall.no'

@app.route('/camera')
def camera():
    return render_template('camera.html')

@app.route('/photo-booth/<wall_id>')
def photo_booth(wall_id):
    return render_template('photobooth.html')

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
    wdl = WallDataLayer()
    wall = wdl.get_by_id(wall_id)
    if wall is None:
        return '', 404
        
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
    qr.add_data(f"{url_for('camera', _external=True)}?w={wall_id}")
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    qr_code_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    svg = qr.make_image(fill='black', image_factory=qrcode.image.svg.SvgPathFillImage)
    qr_svg = svg.to_string().decode('utf-8')

    # get the images from the wall
    images_in_wall = ImageDataLayer().list_images_for_wall(wall_id)
    images_list = sorted(images_in_wall, key=lambda x: x['ts'], reverse=False)
    # add url to the images_list
    for image in images_list:
        image['url'] = url_for('show_image', id=image['id'])

    # console print the url to the camera app
    print(f"{url_for('camera', _external=True)}?w={wall_id}")

    # return the wall
    return render_template('wall.html', 
                           wall_id=wall_id,
                           wall=wall,
                           images=images_list, 
                           qr_png=qr_code_base64, 
                           qr_svg=qr_svg, 
                           camera_url=f"{url_for('camera', _external=True)}?w={wall_id}"
                           )

@app.route('/w/<wall_id>', methods=['POST'])
def upload_image(wall_id):
    # Get the wall
    wall = WallDataLayer().get_by_id(wall_id)
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
    BlobService().upload_image(short_id, request.data)
    url_to_image = BlobService().get_image_url(short_id)
    image.blob_url = url_to_image
    ImageDataLayer().create(image)
    # Update the wall
    wall.image_ids.append(short_id)
    WallDataLayer().update(wall)
    # Broadcast the event
    broadcast_event(Event(EventType.ADD, image, wall.id))
    return {
        'location': url_for('show_image', id=short_id),
        'owner_key': image.owner_key
        }, 201

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
        # check that the owner key matches the wall
        wall = walls.get(image.wall_id, None)
        if wall is None or owner_key != wall.owner_key:
            return '', 403
    # remove the image from its wall
    wall = walls[image.wall_id]
    wall.image_ids.remove(short_id)
    # delete the image
    del images[short_id]
    # broadcast the event
    broadcast_event(Event(EventType.DELETE, image, wall.id))
    return '', 204

@app.route('/i/<id>', methods=['GET'])
def show_image(id):
    try:
        image : Image = ImageDataLayer().get_by_id(id)
        if image is None:
            return '', 404
        data = BlobService().get_image(id)
        return data, 200, {'Content-Type': image.content_type}
    except:
        return '', 404

@app.route('/w/<wall_id>', methods=['PATCH'])
def patch_wall(wall_id):
    # Get the wall
    wall = WallDataLayer().get_by_id(wall_id)
    if wall is None:
        return '', 404
    # get the owner key from the request
    owner_key = request.headers.get('Owner-Key')
    # check that the owner key matches
    if owner_key != wall.owner_key:
        return '', 403
    # load the json data from the request
    data = request.get_json()
    # validate the email address in the data
    if 'email' not in data:
        return '', 400
    # update the email address
    wall.owner_email = data['email']
    WallDataLayer().update(wall)
    # check if the user already exists
    udl = UserDataLayer()
    user = udl.get_by_email(wall.owner_email)
    if user is None:
        user = User(wall.owner_email)
        udl.create(user)
    # render and send claim email
    email_html = render_template('emails/claim.html',
                    logo = get_image_data_url('static/logo.webp'),
                    email=wall.owner_email,
                    wall_link = url_for('validate', wall_id=wall.id, token=user.validation_code, _external=True),
                    current_year = datetime.now(tz=timezone.utc).year
                    )
    EmailService().send_email(
        wall.owner_email, 
        "Take ownership of your LiveWall", 
        email_html)
    # for easy debugging, print the link to the console
    current_full_url = f"{url_for('validate', wall_id=wall.id, token=user.validation_code, _external=True)}"
    print("Confirmation link", current_full_url)
    # we're good
    return '', 204

@app.route('/validate/<wall_id>/<token>', methods=['GET'])
def validate(wall_id, token):
    # find the wall
    wall = WallDataLayer().get_by_id(wall_id)
    if wall is None:
        return '', 404
    # find the user from the wall
    email = wall.owner_email
    found_user = UserDataLayer().get_by_email(email)
    if found_user is None:
        return '', 404
    # check that the token matches
    if str(found_user.validation_code) != str(token):
        return '', 403
    # validate the user
    if not found_user.validated:
        found_user.validated = True
        UserDataLayer().update(found_user)
    # upgrade the wall to owned
    if wall.status != WallStatus.OWNED:
        wall.status = WallStatus.OWNED
        WallDataLayer().update(wall)
        # broadcast the event
        broadcast_event(Event(EventType.UPDATE, None, wall.id))
        # send email to the user of the wall
        email_html = render_template('emails/owner.html',
                        logo = get_image_data_url('static/logo.webp'),
                        email = email,
                        wall_link = url_for('wall', wall_id=wall.id, _external=True) + f"?k={wall.owner_key}",
                        moderation_link = url_for('moderation_page', wall_id=wall.id, key=wall.owner_key, _external=True),
                        user_link = url_for('user_page', user_id=found_user.id, validation_token=found_user.validation_code, _external=True),
                        current_year = datetime.now(tz=timezone.utc).year)
        
        EmailService().send_email(
            email, 
            "Your LiveWall is ready", 
            email_html,
            wait_success=False)
    # redirect the user to the control panel for the wall
    return redirect(url_for('moderation_page', wall_id=wall.id, key=wall.owner_key))

@app.route('/u/<user_id>/<validation_token>', methods=['GET'])
def user_page(user_id, validation_token):
    # find the user
    user = UserDataLayer().get_by_id(user_id)
    if user is None:
        return '', 404
    # check that the token matches
    if user.validation_code != validation_token:
        return '', 403
    # list walls for the user
    walls = WallDataLayer().list_walls_for_user(user.email)
    # find number of images per wall
    for wall in walls:
        images = ImageDataLayer().list_images_for_wall(wall.id)
        wall.num_images = len(images)
        wall.images = images
    # return the control panel
    return render_template('user.html', user=user, walls=walls)

@app.route('/m/<wall_id>/<key>', methods=['GET'])
def moderation_page(wall_id, key):
    # find the wall
    wall = WallDataLayer().get_by_id(wall_id)
    if wall is None:
        return '', 404
    # check that the key matches
    if key != wall.owner_key:
        return '', 403
    # find the matching user
    user = UserDataLayer().get_by_email(wall.owner_email)
    # external link to wall
    wall_external_link = url_for('wall', wall_id=wall.id, _external=True) + f"?k={wall.owner_key}"
    # list the 10 latest images for the wall
    images = ImageDataLayer().list_images_for_wall(wall_id)
    images = sorted(images, key=lambda x: x['ts'], reverse=True)
    # return the control panel
    return render_template('moderation.html', wall=wall, user=user, wall_link=wall_external_link, images=images[:10])

admin_route = shortuuid.uuid()
if DEBUG_MODE:
    admin_route = 'admin'
@app.route(f"/{admin_route}", methods=['GET'])
def admin():
    all_users = UserDataLayer().list_users()
    all_walls = WallDataLayer().list_walls()
    return render_template('admin.html', users=all_users, walls=all_walls, delete_all_url=url_for('admin'))

print(f"Admin", f"http://localhost:3000/{admin_route}")

@app.route(f"/{admin_route}", methods=['DELETE'])
def delete_everything():
    from datalayers import CleanDatabase
    CleanDatabase().clean_everything()
    return '', 204

@app.route('/robots.txt')
def robots_txt():
    response = Response("User-agent: *\nDisallow: /\nAllow: /$", mimetype='text/plain')
    return response

@app.route('/favicon.ico')
def favicon():
    with open('favicon.ico', 'rb') as f:
        return Response(f.read(), mimetype='image/vnd.microsoft.icon')
    
@app.route('/start')
def start():
    # create a new wall and redirect the user there
    wall = Wall()
    WallDataLayer().create(wall)
    return redirect(f"{url_for('wall', wall_id=wall.id)}?k={wall.owner_key}")

print(f"New wall:", f"http://localhost:3000/start")

@app.route('/upgrade/<wall_id>/<owner_key>', methods=['GET'])
def upgrade(wall_id, owner_key):
    wall = WallDataLayer().get_by_id(wall_id)
    if wall is None:
        return '', 404
    if owner_key != wall.owner_key:
        return '', 403
    # if ?canceled=true is in the query string, show a message
    was_canceled = False
    if request.args.get('canceled') == 'true':
        was_canceled = True
    return render_template('upgrade.html', wall=wall, was_canceled=was_canceled, stripe_public_key=STRIPE_PUBLIC_KEY, nonce=shortuuid.uuid())

@app.route('/checkout/<wall_id>/<owner_key>', methods=['POST'])
def initiate_checkout(wall_id, owner_key):
    wall = WallDataLayer().get_by_id(wall_id)
    if wall is None:
        return '', 404
    if owner_key != wall.owner_key:
        return '', 403
    
    customer_email_address = None
    if wall.owner_email is not None:
        customer_email_address = wall.owner_email
    
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price': STRIPE_PRICE_ID,
            'quantity': 1,
        }],
        mode='payment',
        success_url=url_for('transaction_success', wall_id=wall_id, owner_key=wall.owner_key, _external=True),
        cancel_url=url_for('upgrade', wall_id=wall.id, owner_key=owner_key, _external=True) + '?canceled=true',
        payment_intent_data={ # saved with transaction metadata
            'metadata': {
                'site': 'LiveWall',
                'wall_id': wall_id,
                'owner_key': wall.owner_key
            }
        },
        metadata={ # session metadata
            'wall_id': wall_id
        },
        customer_email=customer_email_address
    )

    return {
        'id': session.id
    }

@app.route('/success/<wall_id>/<owner_key>', methods=['GET'])
def transaction_success(wall_id, owner_key):
    return redirect(url_for('wall', wall_id=wall_id, _external=True) + f"?k={owner_key}")

@app.route("/ho2ot7spra", methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    # save the payload to a temporary file in the current directory
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(payload.encode('utf-8'))
        print(f"Saved payload to {f.name}")

    event = None
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_SIGNING_SECRET
        )
    except ValueError as e:
        # Invalid payload
        print(e)
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        print(e)
        return 'Invalid signature', 400
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Extract wall_id from metadata
        wall_id = session['metadata'].get('wall_id')
        
        # Extract customer_email
        customer_email = session['customer_details']['email']
        
        # Check if the transaction succeeded
        payment_status = session.get('payment_status')
        if payment_status == 'paid':
            # Transaction succeeded
            # handle_successful_transaction(wall_id, customer_email, session)
            wall = WallDataLayer().get_by_id(wall_id)
            wall.status = WallStatus.PREMIUM
            if wall.owner_email is None:
                wall.owner_email = customer_email
            WallDataLayer().update(wall)
            # check if the user already exists
            udl = UserDataLayer()
            user = udl.get_by_email(wall.owner_email)
            if user is None:
                user = User(wall.owner_email)
                udl.create(user)
            # send confirmation email
            html_email = render_template('emails/premium.html',
                logo=get_image_data_url('static/logo.webp'),
                email=wall.owner_email,
                wall_link=url_for('wall', wall_id=wall.id, _external=True) + f"?k={wall.owner_key}",
                moderation_link=url_for('moderation_page', wall_id=wall.id, key=wall.owner_key, _external=True),
                current_year=datetime.now(tz=timezone.utc).year,
                expiry=datetime.now(tz=timezone.utc) + timedelta(days=365),
                booth_link=url_for('photo_booth', wall_id=wall.id, _external=True)
                )
            EmailService().send_email(
                wall.owner_email, 
                "Your LiveWall has entered premium mode", 
                html_email,
                wait_success=False)
            # update the page on all screens
            broadcast_event(Event(EventType.UPDATE, None, wall.id))
        else:
            # Transaction failed or is incomplete
            print("Transaction failed")
            #handle_failed_transaction(wall_id, customer_email, session)
            pass
            

    return 'Success', 200

@app.route('/', methods=['POST'])
def create_wall():
    # create a new wall
    wall = Wall()
    WallDataLayer().create(wall)
    # if a user email and validation code are provided, set the wall as owned
    data = request.get_json()
    if 'email' in data and 'validation_code' in data:
        user = UserDataLayer().get_by_email(data['email'])
        if user is None or str(user.validation_code) != str(data['validation_code']):
            return '', 403
        
        wall.owner_email = data['email']
        wall.status = WallStatus.OWNED
        WallDataLayer().update(wall)
    # return the URL to the wall in JSON
    return {
        'url': f"{url_for('wall', wall_id=wall.id, _external=True)}?k={wall.owner_key}"
    }, 201


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')

print(f"Home:", f"http://localhost:3000/")
print(f"External:", f"https://chph.eu.ngrok.io/")

def get_image_data_url(image_path):
    with open(image_path, 'rb') as img_file:
        encoded_string = base64.b64encode(img_file.read()).decode('utf-8')
        return f'data:image/webp;base64,{encoded_string}'
    
@app.route('/email')
def email():
    wall = WallDataLayer().list_walls()[0]
    user = UserDataLayer().list_users()[0]
    email_address = user.email
    # render the template email/owner.html
    email_html = render_template('emails/owner.html', 
                    logo=get_image_data_url('static/logo.webp'),
                    email=email_address,
                    wall_link=url_for('wall', wall_id=wall.id, _external=True) + f"?k={wall.owner_key}",
                    user_link=url_for('user_page', user_id=user.id, validation_token=user.validation_code, _external=True),
                    current_year=datetime.now(tz=timezone.utc).year,
                    )
    
    EmailService().send_email(
        recipientAddress='christopher@frenning.com',
        subject='Test email',
        body=email_html,
        wait_success=False)
    EmailService().send_email(
        recipientAddress='c@perceptron.no',
        subject='Test email',
        body=email_html,
        wait_success=False)
    return 'Email sent', 201

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG_MODE)