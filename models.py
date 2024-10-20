import time
import random
import shortuuid
from enum import Enum
from datetime import datetime, timezone

def normalize_datetime(value):
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value
    val =  datetime.fromisoformat(value.isoformat())
    return val

class User:
    def __init__(self, email):
        self.id = shortuuid.uuid()
        self.email = email
        self.validation_code = str(random.randint(100000, 999999))
        self.validated = False
        self.created = datetime.now(tz=timezone.utc)
        self.modified = datetime.now(tz=timezone.utc)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'validation_code': self.validation_code,
            'validated': self.validated,
            'created': self.created.isoformat(),
            'modified': self.modified.isoformat()
        }
    
    def from_dict(self, data):
        self.id = data['id']
        self.email = data['email']
        self.validation_code = data['validation_code']
        self.validated = data['validated']
        self.created = normalize_datetime(data['created'])
        self.modified = normalize_datetime(data['modified'])

    @classmethod
    def create_from_entity(cls, data):
        user = cls(data['email'])
        user.from_dict(data)
        return user

class Image:
    def __init__(self, id=None, wall_id=None, data=None, content_type=None):
        self.id = id
        self.wall_id = wall_id
        self.data = data
        self.blob_url = None
        self.content_type = content_type
        self.owner_key = shortuuid.uuid()
        self.timestamp = time.time()
        self.created = datetime.now(tz=timezone.utc)
        self.modified = datetime.now(tz=timezone.utc)

    def to_dict(self):
        return {
            'id': self.id,
            'wall_id': self.wall_id,
            'blob_url': self.blob_url,
            'content_type': self.content_type,
            'owner_key': self.owner_key,
            'timestamp': self.timestamp,
            'created': self.created.isoformat(),
            'modified': self.modified.isoformat()
        }
    
    def from_dict(self, data):
        self.id = data['id']
        self.wall_id = data['wall_id']
        self.blob_url = data['blob_url']
        self.content_type = data['content_type']
        self.owner_key = data['owner_key']
        self.timestamp = data['timestamp']
        self.created = normalize_datetime(data['created'])
        self.modified = normalize_datetime(data['modified'])
        self.data = None

class WallStatus(Enum):
    NEW = 'new'
    OWNED = 'owned'
    PREMIUM = 'premium'

class Wall:
    def __init__(self, id=None):
        if id is None:
            id = shortuuid.uuid()

        self.id = id
        self.owner_key = shortuuid.uuid()
        self.image_ids = [] # ids into the images dictionary
        self.owner_email = None
        self.status = WallStatus.NEW
        self.created = datetime.now(tz=timezone.utc)
        self.modified = datetime.now(tz=timezone.utc)

    def to_dict(self):
        return {
            'id': self.id,
            'owner_key': self.owner_key,
            'image_ids': self.image_ids,
            'owner_email': self.owner_email,
            'status': self.status.value,
            'created': self.created.isoformat(),
            'modified': self.modified.isoformat()
        }
    
    def from_dict(self, data):
        self.id = data['id']
        self.owner_key = data['owner_key']
        self.image_ids = data['image_ids'] if 'image_ids' in data else []
        self.owner_email = data['owner_email'] if 'owner_email' in data else None
        self.status = WallStatus(data['status'])
        self.created = normalize_datetime(data['created'])
        self.modified = normalize_datetime(data['modified'])

    @classmethod
    def create_from_entity(cls, data):
        wall = cls(data['id'])
        wall.from_dict(data)
        return wall

class EventType(Enum):
    ADD = 'add'
    DELETE = 'delete'
    UPDATE = 'update'

class Event:
    def __init__(self, type : EventType, image : Image, wall_id : str):
        self.type = type
        self.image = image
        self.wall_id = wall_id
        self.timestamp = time.time()

    def __str__(self) -> str:
        # create json of type, image.id, image.url
        if self.image is None:
            return f'{{"type": "{self.type.value}"}}'
        else:
            return f'{{"type": "{self.type.value}", "id": "{self.image.id}", "url": "/i/{self.image.id}?t={self.image.timestamp}"}}'