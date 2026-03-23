from enum import Enum


class NeurotransmitterEvent(str, Enum):
    LOG = 'spike.log'
    STATUS = 'spike.status'
    BLACKBOARD = 'spike.blackboard'


class LogChannel(str, Enum):
    EXECUTION = 'execution'
    APPLICATION = 'application'


class BiologicalState(str, Enum):
    ERROR = 'ERROR'
    FAILED = 'FAILED'
    STOPPING = 'STOPPING'
    MAXED_OUT = 'MAXED_OUT'
    SPAWN_FAILED = 'SPAWN_FAILED'
    SPAWN_SUCCESS = 'SPAWN_SUCCESS'


# Routing Constants
SYNAPSE_GROUP_PREFIX = 'spike_log_'
RELEASE_METHOD = 'release_neurotransmitter'
