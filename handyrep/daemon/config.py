import os

if not os.environ.has_key('HANDYREP_CONFIG'):
    os.environ['HANDYREP_CONFIG'] = '/srv/handyrep//handyrep/handyrep.conf'
