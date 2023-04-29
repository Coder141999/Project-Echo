

#############################################################################
# This class provides message handling for read and writing JSON messages
# This class interfaces with google cloud for audio data
# This class interfaces with mqtt for message passing
#############################################################################

import paho.mqtt.client as paho
import base64
import json
from google.cloud import storage
import os
from entities.species import Species
import random
from clock import Clock
import logging
logger1 = logging.getLogger('_sys_logger')
        
class CommsManager():
    
    def __init__(self) -> None:
        self.audio_blobs = {}
        self.clock = Clock()
       
    # Initialise communication with MQTT endpoints
    def initialise_communications(self):
        
        logger1.info(f'Initialising Communications')
        
        self.mqtt_client = paho.Client()
        #self.mqtt_client.on_publish = on_mqtt_publish
        # we are using an insure public server for now
        self.mqtt_client.connect(os.environ['MQTT_CLIENT_URL'], int(os.environ['MQTT_CLIENT_PORT']))
        # self.mqtt_client.loop_start()

    # This function uses the google bucket with audio files and
    # leverages the folder names as the official species names
    # Note: to run this you will need to first authenticate
    # See https://github.com/DataBytes-Organisation/Project-Echo/tree/main/src/Prototypes/data#readme
    def gcp_load_species_list(self):
 
        species_names = set()

        storage_client = storage.Client()
        bucket = storage_client.get_bucket(os.environ['BUCKET_NAME'])
        blobs = bucket.list_blobs()  # Get list of files
        for blob in blobs:
            folder_name = blob.name.split('/')[0]
       
            species_names.add(folder_name)
            
            if folder_name in self.audio_blobs:
                self.audio_blobs[folder_name].append(blob)
            else:
                self.audio_blobs[folder_name] = []
                self.audio_blobs[folder_name].append(blob)
        
        # using the names loaded from GCP, construct the Species objects
        species_list = []
        for name in species_names:
            species = Species(name)
            species_list.append(species)
            
        return species_list
 
    # send a random audio message for the given animal at the predicted lla
    def mqtt_send_random_audio_msg(self, animal, predicted_lla) -> None:
        
        # get the timestamp for this event
        timestamp = self.clock.get_time()
        
        # get the species name
        species_name    = animal.getSpecies().getName()
        animal_true_lla = animal.getLLA()
        
        # randomly sample from available audio blobs from this species
        sample_blob = random.sample(self.audio_blobs[species_name], k=1)[0]
        
        # Read the blob's content as a byte array
        logger1.info("Retrieving audio from bucket...")
        audio = sample_blob.download_as_bytes()
        logger1.info("Audio clip download complete.")
        
        # Encode the audio data as a string
        audio_str = self.audio_to_string(audio)
        
        # For now, send filename across for format information
        audio_file = sample_blob.name.split('/')[1]
        
        # TODO create the audio message in correct format
        MQTT_MSG = f'''
        {{
            "timestamp": "{timestamp}",
            "animalEstLLA": [
                {predicted_lla[0]},
                {predicted_lla[1]},
                {predicted_lla[2]}
            ],
            "animalTrueLLA": [
                {animal_true_lla[0]},
                {animal_true_lla[1]},
                {animal_true_lla[2]}
            ],
            "animalLLAUncertainty": 0.0,
            "audioClip": "{audio_str}",
            "audioFile": "{audio_file}"
        }}
        '''
  
        # publish the audio message on the queue
        (rc, mid) = self.mqtt_client.publish(os.environ['MQTT_PUBLISH_URL'], MQTT_MSG, qos=1)
        
        logger1.info(f'Vocalisation Published! Animal {animal.getUUID()} time: {timestamp}')
        
    # this method takes in binary audio data and encodes to string
    def audio_to_string(self, audio_binary) -> str:
        base64_encoded_data = base64.b64encode(audio_binary)
        base64_message = base64_encoded_data.decode('utf-8')
        return base64_message
    
    def string_to_audio(self, audio_string) -> bytes:
        base64_img_bytes = audio_string.encode('utf-8')
        decoded_data = base64.decodebytes(base64_img_bytes)
        return decoded_data
    
    def test(self):
        logger1.info(f'testing MessageManager')
        
        logger1.info(f'Testing GCP endpoint')
        
        species_list = self.gcp_load_species_list()
        for species in species_list:
            logger1.info(f'Found species : {species.getName()}')
        
        # load a test json file containing audio data
        with open('src\Prototypes\data\database\sample_data\events.json', 'r') as file:
            test_json = json.load(file)
            msg = test_json[0]
            logger1.info(f' Loaded message timestamp: {msg["timestamp"]}')
            
            audio_b1 = self.string_to_audio(msg['audioClip'])
            audio_s1 = self.audio_to_string(audio_b1)
            
            audio_b2 = self.string_to_audio(audio_s1)
            audio_s2 = self.audio_to_string(audio_b2)
            
            audio_b3 = self.string_to_audio(audio_s2)
            audio_s3 = self.audio_to_string(audio_b3)
            
            assert audio_s3 == audio_s1, "Strings are not matching!"
            
            logger1.info(f'test completed successfully')
    
        