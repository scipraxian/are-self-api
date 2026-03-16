from enum import Enum


class NeurotransmitterEvent(str, Enum):
    LOG = 'spike.log'
    STATUS = 'spike.status'
    BLACKBOARD = 'spike.blackboard'


class LogChannel(str, Enum):
    EXECUTION = 'execution'
    APPLICATION = 'application'


# Routing Constants
SYNAPSE_GROUP_PREFIX = 'spike_log_'
RELEASE_METHOD = 'release_neurotransmitter'
