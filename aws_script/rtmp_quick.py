#!/usr/bin/env python3
# (C) 2025 A Parent Media Company. MediaLive RTMP push input setup video engineering test.
import boto3, argparse, uuid, re, ipaddress, json, sys, random, string
from botocore.exceptions import ClientError

def load_config(file_path): #read json config file instead of command line.
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        sys.exit(f"Error loading config: {e}")

def generate_name(name=None): #input name generation
    if not name:
        return f"rtmp-input-{uuid.uuid4()}"
    suffix = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6)) #add six random ascii characters for name uniqueness.
    return f"{name}-{suffix}"

def create_security_group(client, cidr): #create CIDR sg 
    try:
        response = client.create_input_security_group(
            WhitelistRules=[{'Cidr': cidr}],
            Tags={'AutoCreated': 'True'}
        )
        return response['SecurityGroup']['Id']
    except ClientError as e:
        sys.exit(f"Error creating security group: {e}")

def create_network(client, name, ip_pools, routes=None): #validate and process ON_PREMISES inputs.
    try:
        request = {
            'Name': name,
            'IpPools': ip_pools
        }
        if routes:
            request['Routes'] = routes
        
        response = client.create_network(**request)
        return response['Id']
    except ClientError as e:
        sys.exit(f"Error creating network: {e}")

## MAIN LOGIC ##
def create_rtmp_input(args): 
    try:
        client = boto3.client('medialive', region_name=args.region)

        if args.config:   # Use config file if provided
            config = load_config(args.config)
            response = client.create_input(**config)
            return response
        
        input_name = generate_name(args.name) # Basic request configuration
        location = "ON_PREMISES" if args.source_type == "ON_PREMISES" else "AWS"
        
        input_request = { #RTMP publishing points app/instance names.
            'Name': input_name,
            'Type': 'RTMP_PUSH',
            'InputNetworkLocation': location,
            'Destinations': [
                {'StreamName': f"{args.app_name}/{args.app_instance}"},
                {'StreamName': f"{args.secondary_app_name or args.app_name}/{args.secondary_app_instance or args.app_instance}"}
            ]
        }
        
        if args.tags: # Add cusotm tags
            input_request['Tags'] = {k: v for tag in args.tags for k, v in [tag.split('=', 1)] if '=' in tag}
        
        if args.source_type == 'AWS': #PROCESS AWS
            if args.security_group and args.security_group.startswith('sg-'):
                input_request['InputSecurityGroups'] = [args.security_group]
            else:
                cidr = args.security_group if args.security_group else "0.0.0.0/0"
                sg_id = create_security_group(client, cidr)
                input_request['InputSecurityGroups'] = [sg_id]
                
        elif args.source_type == 'AWS_VPC':  #PROCESS AWS_VPC
            if not args.subnets or len(args.subnets) < 2:
                sys.exit("Error: AWS_VPC requires at least 2 subnets")
                
            vpc_config = {'SubnetIds': args.subnets[:2]}
            if args.security_group:
                vpc_config['SecurityGroupIds'] = [args.security_group]
            
            input_request['Vpc'] = vpc_config
            input_request['RoleArn'] = args.role_arn
            
        elif args.source_type == 'ON_PREMISES': #PROCESS ON_PREMISES
            network_id = args.network
            if not network_id:
                # Create basic network if none provided
                ip_pools = [{'Cidr': "10.0.0.0/24"}]
                network_id = create_network(client, f"network-{uuid.uuid4()}", ip_pools)
            
            for dest in input_request['Destinations']:
                dest['Network'] = network_id
                if args.static_ip:
                    dest['StaticIpAddress'] = args.static_ip
                if args.network_routes:
                    dest['NetworkRoutes'] = [
                        {'Cidr': r.split(':', 1)[0], 'Gateway': r.split(':', 1)[1]} if ':' in r 
                        else {'Cidr': r} for r in args.network_routes
                    ]
        
        response = client.create_input(**input_request)
        return response
    except ClientError as e:
        sys.exit(f"Error: {e}")

def format_output(response): # nice JSOPN report.
    input_info = response.get('Input', {})
    attached = len(input_info.get('AttachedChannels', [])) > 0
    
    report = {
        "Input ID": input_info.get('Id', 'N/A'),
        "Name": input_info.get('Name', 'N/A'),
        "State": "attached" if attached else "detached",
        "Attached Channels": input_info.get('AttachedChannels', []),
        "Input ARN": input_info.get('Arn', 'N/A'),
        "Type": input_info.get('Type', 'N/A'),
        "Input Network Location": input_info.get('InputNetworkLocation', 'N/A'),
        "Endpoints": [],
        "Input Security Groups": input_info.get('SecurityGroups', []),
        "Tags": input_info.get('Tags', {})
    }
    
    for dest in input_info.get('Destinations', []):
        endpoint = {
            "URL": dest.get('Url', 'N/A'),
            "IPv4": dest.get('Ip', 'N/A'),
            "Port": dest.get('Port', 'N/A'),
            "Network": dest.get('Network', 'N/A'),
            "Network Routes": dest.get('NetworkRoutes', [])
        }
        report["Endpoints"].append(endpoint)
    
    return report

def parse_args(): #Command line args.
    parser = argparse.ArgumentParser(description='Create AWS MediaLive RTMP Push Input')
    parser.add_argument('--config', type=str, help='Path to JSON configuration file')
    parser.add_argument('--name', type=str, help='Name prefix for the RTMP input')
    parser.add_argument('--region', type=str, default='us-east-2', help='AWS region')
    parser.add_argument('--source-type', type=str, default='AWS', choices=['AWS', 'AWS_VPC', 'ON_PREMISES'])
    parser.add_argument('--app-name', type=str, help='Application name')
    parser.add_argument('--app-instance', type=str, help='Application instance')
    parser.add_argument('--secondary-app-name', type=str, help='Secondary application name')
    parser.add_argument('--secondary-app-instance', type=str, help='Secondary application instance')
    parser.add_argument('--security-group', type=str, help='Security group ID or CIDR')
    parser.add_argument('--subnets', type=str, nargs='+', help='Subnet IDs for AWS_VPC')
    parser.add_argument('--role-arn', type=str, help='Role ARN for AWS_VPC')
    parser.add_argument('--network', type=str, help='Network ID for ON_PREMISES')
    parser.add_argument('--static-ip', type=str, help='Static IP for ON_PREMISES')
    parser.add_argument('--network-routes', type=str, nargs='+', help='Routes (CIDR:gateway)')
    parser.add_argument('--tags', type=str, nargs='+', help='Tags (Key=Value)')
    return parser.parse_args()

def main():
    try:
        args = parse_args()
        
        # Minimal validation
        if not args.config and (not args.source_type or not args.app_name or not args.app_instance):
            sys.exit("Error: --config or --source-type, --app-name, and --app-instance are required")
        
        response = create_rtmp_input(args)
        report = format_output(response)
        
        print(json.dumps(report, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1

if __name__ == "__main__":
    sys.exit(main())