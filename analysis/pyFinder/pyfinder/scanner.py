import docker
import docker.errors
from subprocess import Popen, PIPE, STDOUT
import re
from .container import Container
from .utils import *
from .client_images_service import ClientImages
from .client_daemon import ClientDaemon
from .client_dockerhub import ClientHub
from .client_software import ClientSoftware
from .consumer_rabbit import ConsumerRabbit
from .utils import get_logger
import logging


class Scanner:
    def __init__(self, amqp_url='amqp://guest:guest@127.0.0.1:5672', exchange=None, queue=None, route_key=None,
                 software_url="http://127.0.0.1:3001/api/software",
                 images_url="http://127.0.0.1:3000/api/images",
                 hub_url="https://hub.docker.com/",
                 rmi=True):

        self.rmi = rmi  # remove an image ofter the scan

        self.logger = get_logger(__name__, logging.DEBUG)

        # client of software service: the service that return the software to search in the images.
        self.client_software = ClientSoftware(api_url=software_url)

        # client for interacting with the docker daemon on the host
        self.client_daemon = ClientDaemon(base_url='unix://var/run/docker.sock')

        # rabbit consumer for receiving the images, on_message_callback is called when a message is received
        self.consumer = ConsumerRabbit(amqp_url=amqp_url,
                                       exchange=exchange,
                                       queue=queue,
                                       route_key=route_key,
                                       on_msg_callback=self.on_message)

        # the clientApi interacts with the server api in order to post the image description
        self.client_images = ClientImages(images_url=images_url)
        # host_service=host_images, port_service=port_images, url_path=path_images)

        # the client hub interacts with the docker Hub registry
        self.client_hub = ClientHub(docker_hub_endpoint=hub_url)

    def on_message(self, json_message):
        """
        This is the CALLBACK function that is called when the consumer Rabbit receives a message.
        """
        self.logger.info("Received message:" + str(json_message))
        # first method called when an image name is received
        self.process_repo_name(json_message['name'])

    def run(self):
        """
        Run the scanner starting the consumer client of the RabbitMQ server.
        :return:
        """

        try:
            self.consumer.run()
        except KeyboardInterrupt:
            self.consumer.stop()

    def process_repo_name(self, repo_name):
        self.logger.info("[" + repo_name + "] Processing image")
        list_tags = self.client_hub.get_all_tags(repo_name)
        tag = "latest"
        if tag in list_tags:
            # TODO; is new must contains also the tag latest ...
            if self.client_images.is_new(repo_name):  # the image is totally new
                dict_image = self.scan(repo_name, tag)
                self.client_images.post_image(dict_image)  # POST the description of the image
                self.logger.info("[" + repo_name + "]  uploaded the new image description")
            elif self.client_images.must_scanned(repo_name):  # the image must be scan again
                self.logger.debug("[" + repo_name + "] is present into images server but must be scan again")
                dict_image = self.scan(repo_name, tag)
                self.client_images.put_image(dict_image)  # PUT the new image description of the image
                self.logger.info("[" + repo_name + "] updated the image description")
            else:
                self.logger.info("[" + repo_name + "] already up to date.")

    def scan(self, repo_name, tag="latest"):

        self.client_daemon.pull_image(repo_name, tag)
        #self.client_daemon.pull(repo_name, tag)

        dict_image = {}
        dict_image["repo_name"] = repo_name
        self.logger.info('[{0}] start scanning'.format(repo_name))

        self.info_docker_hub(repo_name, dict_image, tag)
        self.info_dofinder(repo_name, dict_image, tag)

        self.logger.info('[{0}] finish scanning'.format(repo_name))
        dict_image['last_scan'] = str(datetime.datetime.now())

        if self.rmi:
            try:
                self.client_daemon.remove_image(repo_name, force=True)
                self.logger.info('[{0}] removed image'.format(repo_name))
            except docker.errors.NotFound as e:
                self.logger.error(e)
        return dict_image

    # def info_inspect(self, repo_name, dict_image):
    #     """
    #      docker inspect IMAGE
    #     """
    #     self.logger.info'[{}] docker inspect ... '.format(repo_name))
    #     dict_inspect = self.client_daemon.inspect_image(repo_name)
    #     #dict_image['size'] = dict_inspect['Size']

    def info_docker_hub(self, repo_name, dict_image, tag):
        """
        Download the image information among Docker API v2.
        :param repo_name:
        :param dict_image:
        :return:
        """
        self.logger.info('[{}] adding Docker Hub info ... '.format(repo_name))

        # take info from the repository
        # {"user": "dido", "name": "webofficina", "namespace": "dido", "status": 1,
        #  "description": "Automated repo for the webOfficina gitHub repository", "is_private": false,
        #  "is_automated": true, "can_edit": false, "star_count": 0, "pull_count": 40,
        #  "last_updated": "2016-06-12T15:46:21.454420Z", "has_starred": false,
        #  "full_description": "# webOfficina\nWebOfficina is a web application"
        #  "permissions": {"read": true, "write": false, "admin": false}}
        json_response = self.client_hub.get_json_repo(repo_name)

        if json_response:
            if 'description' in json_response:
                dict_image['description'] = json_response['description']
            if 'star_count' in json_response:
                # dict_image['star_count'] = json_response['star_count']
                dict_image['stars'] = json_response['star_count']
            if 'pull_count' in json_response:
                # dict_image['pull_count'] = json_response['pull_count']
                dict_image['pulls'] = json_response['pull_count']


        # take info from a tag
        # {"name": "latest", "full_size": 279654175, "id": 1720126, "repository": 479046, "creator": 534858,
        #  "last_updater": 534858, "last_updated": "2016-06-12T15:46:18.292828Z", "image_id": null, "v2": true,
        #  "platforms": [5]}
        json_response = self.client_hub.get_json_tag(repo_name, tag)

        if 'name' in json_response:
            dict_image['tag'] = json_response['name']
        if 'last_updated' in json_response:
            dict_image['last_updated'] = json_response['last_updated']
        if 'full_size' in json_response:
            dict_image['size'] = json_response['full_size']

    def info_dofinder(self, image_name, dict_image, tag):

        repo_name_tag = image_name + ":" + tag
        self.logger.info('[{}] searching software ... '.format(repo_name_tag))

        # with Container(repo_name) as c:

        # search distribution Operating system,
        for cmd, regex in self.client_software.get_system():  # self._get_sys(self.versionCommands):
            try:
                distro = self.version_from_regex(repo_name_tag, cmd, regex)
                if distro:
                    dict_image['distro'] = distro
                # output = self.run_command(repo_name, cmd)
                # p = re.compile(reg)
                # match = p.search(output)
                # if match:
                #     # take the non-capturing group: only the matches, group[0] return all the match
                #     dist = match.group(0)
                #     dict_image['distro'] = dist
                # else:
                #     self.logger.debug("[{0}] not found {1}".format(repo_name, cmd))
            except docker.errors.NotFound as e:
                self.logger.error(e)
                #   with Container(repo_name) as c:

        # search binary versions
        softwares = []
        for sw in self.client_software.get_software():  # self._get_bins(self.versionCommands):
            try:
                software = sw['name']
                command = software+" " + sw['cmd']
                #cmd = sw['cmd']
                regex = sw['regex']
                version = self.version_from_regex(repo_name_tag, command, regex)
                if version:
                    softwares.append({'software': software, 'ver': version})
            except docker.errors.NotFound as e:
                self.logger.error(e)
        dict_image['softwares'] = softwares

    def version_from_regex(self, repo_name, command, regex):
        output = self.run_command(repo_name, command)
        p = re.compile(regex)
        match = p.search(output)
        if match:
            version = match.group(0)
            self.logger.debug("[{0}] found in {1}".format(command, repo_name))
            return version
        else:
            self.logger.debug("[{0}] NOT found in {1}".format(command, repo_name))
            return None


    def run_command(self, repo_name, command):
        """Just like 'docker run CMD'.
        Return the output of the command.
        """
        # Popen version: PROBLEM; the scanner is executed in a container and docker in not installed inside.
        # self.logger.debug("Executing in " + repo_name+": "+program +" "+option)
        # p = Popen(['docker', 'run', '--rm', repo_name, program, option], stdout=PIPE, stderr=STDOUT)
        # out = p.stdout.read().decode()
        # return out

        #ver_command = program + " " + option
        self.logger.info("[{0}] running command {1}".format(repo_name, command))
        container_id = self.client_daemon.create_container(image=repo_name,
                                                           entrypoint=command,
                                                           tty=True,
                                                           stdin_open=True,

                                                         )['Id']
        try:
            self.client_daemon.start(container=container_id)
        except docker.errors.APIError as e:
            self.logger.error(e)
            return " "
        #self.logger.debug("Searching [{0}] in {1} ...".format(command, repo_name))
        self.client_daemon.wait(container_id)
        output = self.client_daemon.logs(container=container_id)
        self.client_daemon.remove_container(container_id)
        self.logger.debug("Removed container "+container_id)
        return output.decode()

    # def pull_officials(self):
    #     # TODO excpetion raise for the connection to docker hub
    #     # download all the official library
    #     images_libraries = self.client_hub.crawl_official_images()
    #     self.logger.info("[" + str(images_libraries)+ "] number of official images to pull...")
    #     for image in images_libraries:
    #         try:
    #
    #             self.client_daemon.pull_image(image)
    #         except docker.errors.APIError:
    #             self.logger.exception("Docker api error")
    #             pass
