FROM node:argon
# node.js and npm already installed

# Create code directore that contain the source code
RUN mkdir -p /code
WORKDIR /code

# Install app dependencies
COPY package.json /code
RUN npm install

# Bundle app source
COPY . /code

#commnand to run the app
ENTRYPOINT [ "npm", "start" ]