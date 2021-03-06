import datetime
import time
import logging
import pickle
#from .client_dockerhub import ClientHub


def string_to_date(string_date):
    return datetime.datetime(*time.strptime(string_date, "%Y-%m-%dT%H:%M:%S.%fZ")[:7])


def get_logger(name_class, level=logging.DEBUG):

    logger = logging.getLogger(name_class)
    # logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(level)
    #print(name_class + ": " + level + " logging level setted")

    # create file handler which logs even debug messages
    #fh = logging.FileHandler(name_file)
    #fh.setLevel(level)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # create formatter and add it to the handlers
    LOG_FORMAT = ('%(levelname) -3s %(asctime)s %(name) -15s %(funcName) '
              '-15s %(lineno) -5d: %(message)s')
    formatter = logging.Formatter(LOG_FORMAT)
    #fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    #logger.addHandler(fh)
    logger.addHandler(ch)

    assert isinstance(logger, logging.Logger)
    return logger
