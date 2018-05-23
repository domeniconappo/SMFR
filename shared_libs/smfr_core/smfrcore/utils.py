"""
Core Utils module
"""


def _running_in_docker():
    """
    Check if the calling code is running in a Docker
    :return: True if caller code is running inside a Docker container
    :rtype: bool
    """
    with open('/proc/1/cgroup', 'rt') as f:
        return 'docker' in f.read()


RUNNING_IN_DOCKER = _running_in_docker()