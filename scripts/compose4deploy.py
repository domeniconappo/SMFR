from copy import deepcopy
import argparse
import sys
import yaml


class ParserHelpOnError(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('error: %s\n' % message)
        self.print_help()
        sys.exit(2)

    def add_args(self):
        self.add_argument('-i', '--input', required=True, default='./docker-compose-parsed.yaml',
                          help='Path to input docker-compose file', metavar='input')
        self.add_argument('-o', '--output',
                          help='Path to the output docker-compose file, cleaned for docker stack deploy command.',
                          default='./docker-compose-4deploy.yaml', metavar='output')


def clean_compose(d_in):
    d_out = deepcopy(d_in)
    for service in d_out['services']:
        if service in ('annotator', 'geocoder', 'web', 'restserver', 'persister', 'aggregator', 'products',) \
                and 'volumes' in d_out['services'][service]:
            if service != 'products':
                del d_out['services'][service]['volumes']
            else:
                cleaned_volumes = []
                for v in d_out['services'][service]['volumes']:
                    if 'src' in v:
                        continue
                    cleaned_volumes.append(v)
                d_out['services'][service]['volumes'] = cleaned_volumes
    return d_out


def main():
    parser = ParserHelpOnError(description='Produce a compatible docker-compose.yaml file to use with '
                                           '`docker stack deploy`')

    parser.add_args()
    parsed_args = parser.parse_args()
    input_path = parsed_args.input
    output_path = parsed_args.output
    with open(input_path) as inp:
        d = yaml.load(inp)
        o = clean_compose(d)
        with open(output_path, 'w') as out:
            yaml.dump(o, out, default_flow_style=False)


if __name__ == '__main__':
    sys.exit(main())
