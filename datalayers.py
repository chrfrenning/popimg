import os

from datetime import datetime
from azure.data.tables import TableServiceClient
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueServiceClient
from azure.core.exceptions import ResourceNotFoundError

from config import AZURE_STORAGE_CS
from models import User, Image, Wall, WallStatus



class UserDataLayer:
    def __init__(self, connection_string = AZURE_STORAGE_CS, table_name = 'users'):
        self.connection_string = connection_string
        self.table_name = table_name
        self.table_service_client = TableServiceClient.from_connection_string(conn_str=connection_string)
        self.table_client = self.table_service_client.get_table_client(table_name=table_name)

    def create(self, user):
        entity = user.to_dict()
        entity['PartitionKey'] = 'id'
        entity['RowKey'] = user.id
        self.table_client.create_entity(entity=entity)
        # create an index based on email
        entity['PartitionKey'] = 'email'
        entity['RowKey'] = user.email
        self.table_client.create_entity(entity=entity)

    def get_by_id(self, id):
        try:
            entity = self.table_client.get_entity(partition_key='id', row_key=id)
            usr = User(None)
            usr.from_dict(entity)
            return usr
        except ResourceNotFoundError:
            return None
        
    def get_by_email(self, email):
        try:
            entity = self.table_client.get_entity(partition_key='email', row_key=email)
            usr = User(None)
            usr.from_dict(entity)
            return usr
        except ResourceNotFoundError:
            return None
        
    def update(self, user):
        entity = user.to_dict()
        entity['PartitionKey'] = 'id'
        entity['RowKey'] = user.id
        self.table_client.update_entity(mode='merge', entity=entity)
        # update the index based on email
        entity['PartitionKey'] = 'email'
        entity['RowKey'] = user.email
        self.table_client.update_entity(mode='merge', entity=entity)

    def delete(self, user):
        self.table_client.delete_entity(partition_key='id', row_key=user.id)
        self.table_client.delete_entity(partition_key='email', row_key=user.email)

    def list_users(self):
        query = "PartitionKey eq 'id'"
        entities = self.table_client.query_entities(query)
        return [User.create_from_entity(entity) for entity in entities]



class WallDataLayer:
    def __init__(self, connection_string = AZURE_STORAGE_CS, table_name = 'walls'):
        self.connection_string = connection_string
        self.table_name = table_name
        self.table_service_client = TableServiceClient.from_connection_string(conn_str=connection_string)
        self.table_client = self.table_service_client.get_table_client(table_name=table_name)

    def create(self, wall):
        entity = wall.to_dict()
        entity['PartitionKey'] = 'wall'
        entity['RowKey'] = wall.id
        del entity['image_ids']
        self.table_client.create_entity(entity=entity)

    def get_by_id(self, id):
        try:
            entity = self.table_client.get_entity(partition_key='wall', row_key=id)
            wall = Wall(None)
            wall.from_dict(entity)
            return wall
        except ResourceNotFoundError:
            return None
        
    def add_image_to_wall(self, wall_id, image_id):
        entity = {
            'PartitionKey': wall_id,
            'RowKey': image_id,
            'Timestamp' : datetime.now().isoformat()
        }
        self.table_client.upsert_entity(entity=entity)

    def remove_image_from_wall(self, wall_id, image_id):
        self.table_client.delete_entity(partition_key=wall_id, row_key=image_id)

    def update(self, wall):
        entity = wall.to_dict()
        entity['PartitionKey'] = 'wall'
        entity['RowKey'] = wall.id
        del entity['image_ids']
        self.table_client.update_entity(mode='merge', entity=entity)
        # if the wall is owned, create an index to the owner email
        if wall.status == WallStatus.OWNED:
            entity['PartitionKey'] = wall.owner_email
            entity['RowKey'] = wall.id
            self.table_client.upsert_entity(entity=entity)

    def delete(self, wall):
        self.table_client.delete_entity(partition_key='id', row_key=wall.id)

    def list_walls(self):
        query = "PartitionKey eq 'wall'"
        entities = self.table_client.query_entities(query)
        return [Wall.create_from_entity(entity) for entity in entities]
    
    def list_walls_for_user(self, email):
        query = f"PartitionKey eq '{email}'"
        entities = self.table_client.query_entities(query)
        return [Wall.create_from_entity(entity) for entity in entities]



class ImageDataLayer:
    def __init__(self, connection_string = AZURE_STORAGE_CS, table_name = 'images'):
        self.connection_string = connection_string
        self.table_name = table_name
        self.table_service_client = TableServiceClient.from_connection_string(conn_str=connection_string)
        self.table_client = self.table_service_client.get_table_client(table_name=table_name)

    def create(self, image):
        entity = image.to_dict()
        # associate the image with the wall
        entity['PartitionKey'] = image.wall_id
        entity['RowKey'] = image.id
        self.table_client.create_entity(entity=entity)
        # create an index of the image id
        p, k = self.__split_id(image.id)
        entity['PartitionKey'] = p
        entity['RowKey'] = k
        self.table_client.create_entity(entity=entity)

    def get_by_id(self, image_id):
        try:
            p, r = self.__split_id(image_id)
            entity = self.table_client.get_entity(partition_key=p, row_key=r)
            img = Image(None)
            img.from_dict(entity)
            return img
        except ResourceNotFoundError:
            return None

    def update(self, image):
        entity = image.to_dict()
        entity['PartitionKey'] = image.wall_id
        entity['RowKey'] = image.id
        self.table_client.update_entity(mode='merge', entity=entity)
        # update the index of the image id
        p, k = self.__split_id(image.id)
        entity['PartitionKey'] = p
        entity['RowKey'] = k
        self.table_client.update_entity(mode='merge', entity=entity)

    def delete(self, image):
        p, k = self.__split_id(image.id)
        self.table_client.delete_entity(partition_key=p, row_key=k)
        self.table_client.delete_entity(partition_key=image.wall_id, row_key=image.id)

    def list_images_for_wall(self, wall_id):
        query = f"PartitionKey eq '{wall_id}'"
        entities = self.table_client.query_entities(query, select=['RowKey', 'timestamp'])
        return [ {"id": entity['RowKey'], "ts": entity['timestamp']} for entity in entities]

    @staticmethod
    def __split_id(id):
        half = len(id) // 2
        return id[:half], id[half:]
    

class CleanDatabase:
    def __init__(self, connection_string = AZURE_STORAGE_CS):
        self.connection_string = connection_string
        self.table_service_client = TableServiceClient.from_connection_string(conn_str=connection_string)
        self.queue_service_client = QueueServiceClient.from_connection_string(conn_str=connection_string)
        self.blob_service_client = BlobServiceClient.from_connection_string(conn_str=connection_string)

    def clean_everything(self):
        for table in self.table_service_client.list_tables():
            self._clean_table(table.name)
        for queue in self.queue_service_client.list_queues():
            self._clean_queue(queue.name)
        for container in self.blob_service_client.list_containers():
            self._clean_blob_container(container.name)

    def _clean_table(self, table_name):
        table_service_client = TableServiceClient.from_connection_string(self.connection_string)
        table_client = table_service_client.get_table_client(table_name)
        for entity in table_client.list_entities():
            table_client.delete_entity(partition_key=entity['PartitionKey'], row_key=entity['RowKey'])

    def _clean_queue(self, queue_name):
        queue_service_client = QueueServiceClient.from_connection_string(self.connection_string)
        queue_client = queue_service_client.get_queue_client(queue_name)
        for message in queue_client.receive_messages():
            queue_client.delete_message(message)

    def _clean_blob_container(self, container_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        container_client = blob_service_client.get_container_client(container_name)
        for blob in container_client.list_blobs():
            container_client.delete_blob(blob)
