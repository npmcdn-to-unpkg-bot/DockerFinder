import json
import pickle
from .publisher_rabbit import PublisherRabbit
from .client_dockerhub import ClientHub
import logging
from .utils import get_logger


class Crawler:

    def __init__(self, exchange="dofinder",
                 queue="images",
                 route_key="images.scan",
                 amqp_url='amqp://guest:guest@127.0.0.1:5672',
                 hub_url="https://hub.docker.com/"
    ):
                 #port_rabbit=5672, host_rabbit='localhost', queue_rabbit="dofinder"):

        self.logger = get_logger(__name__, logging.DEBUG)

        # publish the images downloaded into the rabbitMQ server.
        self.publisher = PublisherRabbit(amqp_url, exchange=exchange, queue= queue, route_key=route_key)
        self.logger.info("Publisher rabbit initialized: exchange=" +exchange+", queue="+queue+" route key="+route_key)

        # Client hub in order to get the images
        self.client_hub = ClientHub(docker_hub_endpoint=hub_url)

    def run(self, from_page=1, page_size=10, max_images=100):
        """
        Starts the publisher of the RabbitMQ server, and send to the images crawled with the crawl() method.
        :param from_page:  the starting page into the Docker Hub.
        :param page_size:  is the number of images per image that Docker Hub return.
        :param max_images:  the number of images  name to downloads.
        :return:
        """
        try:
            self.publisher.run(images_generator_function=self.crawl(from_page=from_page, page_size=page_size, max_images=max_images))
        except KeyboardInterrupt:
            self.publisher.stop()

    def filter_tag_latest(self, repo_name):
        """

        :param repo_name: the name of a repository
        :return: True if the image must be downloaded, Flase if must be discarded
        """
        list_tags = self.client_hub.get_all_tags(repo_name)
        if list_tags and 'latest' in list_tags:  # only the images that  contains "latest" tag
            json_image_latest = self.client_hub.get_json_tag(repo_name, tag='latest')
            size  =  json_image_latest['full_size']
            if size > 0:
                self.logger.debug("[ " + repo_name + " ] is selected: tag=latest, size="+str(size))
                return True
            else:
                return False
        else:
            return False

    def crawl(self, from_page=1, page_size=10, max_images=100):
        """
        The crawl() is a generator function. It crawls the docker images name from the Docker HUb.
        IT return a JSON of the image .
        :param from_page:  the starting page into the Docker Hub.
        :param page_size:  is the number of images per image that Docker Hub return.
        :param max_images:  the number of images  name to downloads.
        :return:  generator of JSON images description
        """


        #self.logger.info("Crawling the images from the docker Hub...")
        sent_images = 0
        for list_images in self.client_hub.crawl_images(page=from_page, page_size=page_size, max_images=max_images,
                                                        filter_images=self.filter_tag_latest):
            for image in list_images:
                repo_name = image['repo_name']
                sent_images += 1
                yield json.dumps({"name": repo_name})
        self.logger.info("Number of images sent to RabbtiMQ: {0}\n".format(str(sent_images)))

