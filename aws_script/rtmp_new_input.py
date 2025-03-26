#!/usr/bin/env python3
''' 
(C) 2025 A Parent Media Company.
Internal company use only.
Video eng test.
AWS MediaLive encoder input setup: RTMP push via ON_PREMISE, AWS or AWS_VPC.
by mediastream@gmail.com Dennis Perov
mini report
'''
import boto3     # to API with AWS subsystems
import argparse  # parse command line args
import uuid      # generate compliant UUID
import re        # reg ex checks validity of names
import ipaddress # validates IP addresses
import json      # JSON format to output a nicer report. So a script can be used in a prod chain and API via json
import sys       # properly return exit codes to the system on exit
from botocore.exceptions import ClientError  # handles error messages from AWS on IP address occupation and sec_group creation.
import random, string # for a more accurate rename function.

def load_config_file(file_path):
    #Load configuration from JSON file
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config file: {e}")
        return None

def validate_name(medialive_client, name, attempt=0):
    #Validate input name with retry logic for name conflicts. 3 tries to append a random suffix
    if not name:
        return f"rtmp-input-{uuid.uuid4()}"
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError("Input name must be alphanumeric with hyphens/underscores")
    
    try:
        existing_inputs = medialive_client.list_inputs()['Inputs']
        if any(input_info.get('Name') == name for input_info in existing_inputs):
            if attempt >= 3:
                raise ValueError(f"Could not generate unique name after 3 attempts")
            
            suffix = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6)) # generate 6 digit long random string
            new_name = f"{name}-{suffix}"
            print(f"Warning: Name '{name}' exists, trying '{new_name}'")
            return validate_name(medialive_client, new_name, attempt + 1)
        
        return name
    except ClientError as e:
        print(f"Warning: Name check failed: {e}")
        return name

def get_available_resources(region):
    """Get available AWS resources"""
    ec2 = boto3.client('ec2', region_name=region)
    try:
        subnets = ec2.describe_subnets()['Subnets']
        security_groups = ec2.describe_security_groups()['SecurityGroups']
        return subnets, security_groups
    except ClientError as e:
        print(f"Error fetching resources: {e}")
        return [], []

def get_az_for_subnet(subnet_id, all_subnets):
    """Get availability zone for a subnet"""
    for subnet in all_subnets:
        if subnet['SubnetId'] == subnet_id:
            return subnet.get('AvailabilityZone', 'Unknown')
    return 'Unknown'

def select_resources(items, prompt, multiple=False, min_count=1):
    """Let user select resources interactively"""
    if not items:
        print(f"No {prompt}s available in this account/region.")
        return []
    
    print(f"\nAvailable {prompt}s:")
    for i, item in enumerate(items, 1):
        if 'SubnetId' in item:
            print(f"{i}. {item['SubnetId']} - {item.get('CidrBlock', 'N/A')} - {item.get('AvailabilityZone', 'N/A')}")
        else:  # Security Group
            print(f"{i}. {item['GroupId']} - {item.get('GroupName', 'N/A')}")
    
    while True:
        selection = input(f"\nSelect {prompt}(s) (e.g., '1,2' or '2-4,6'): ")
        try:
            indices = set()
            for part in selection.split(','):
                part = part.strip()
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    if 1 <= start <= end <= len(items):
                        indices.update(range(start, end + 1))
                    else:
                        raise ValueError(f"Invalid range: {part}")
                else:
                    value = int(part)
                    if 1 <= value <= len(items):
                        indices.add(value)
                    else:
                        raise ValueError(f"Invalid selection: {value}")
            
            if len(indices) < min_count:
                print(f"Please select at least {min_count} {prompt}(s).")
                continue
                
            if 'SubnetId' in items[0]:
                return [items[i-1]['SubnetId'] for i in sorted(indices)]
            else:
                return [items[i-1]['GroupId'] for i in sorted(indices)]
                
        except (ValueError, IndexError) as e:
            print(f"Invalid selection: {e}. Please try again.")

def validate_cidr(cidr):
    """Validate CIDR notation"""
    try:
        ipaddress.ip_network(cidr)
        return True
    except ValueError:
        return False

def get_available_security_groups(medialive_client):
    #Get MediaLive input security groups vs. AWS_sg for VPC.
    try:
        response = medialive_client.list_input_security_groups()
        return response.get('InputSecurityGroups', [])
    except ClientError as e:
        print(f"Error fetching MediaLive security groups: {e}")
        return []

def get_available_networks(medialive_client):
    """Get available MediaLive networks"""
    try:
        response = medialive_client.list_networks()
        return response.get('Networks', [])
    except ClientError as e:
        print(f"Error fetching networks: {e}")
        return []

def create_medialive_network(medialive_client, name, ip_pools, routes=None):
    """Create a new MediaLive network for ON_PREMISES inputs"""
    request = {
        'Name': name,
        'IpPools': ip_pools
    }
    
    if routes:
        request['Routes'] = routes
    
    try:
        response = medialive_client.create_network(**request)
        
        # ID is directly in response, not in a nested 'Network' object
        if 'Id' in response:
            network_id = response['Id']
            print(f"Created network '{name}' with ID: {network_id}")
            return network_id
        else:
            print(f"Error: Unexpected response format: {response}")
            return None
    except ClientError as e:
        print(f"Error creating network: {e}")
        return None
        
     
def create_new_network(medialive_client):
    """Create a new network interactively"""
    name = input("Enter network name: ")
    
    ip_pools = []
    while True:
        cidr = input("Enter IP pool CIDR (or leave empty to finish adding pools): ")
        if not cidr:
            break
        
        if validate_cidr(cidr):
            ip_pools.append({'Cidr': cidr})
        else:
            print("Invalid CIDR format. Please try again.")
    
    if not ip_pools:
        print("At least one IP pool is required.")
        return create_new_network(medialive_client)
    
    routes = []
    add_routes = input("Do you want to add network routes? (y/n): ").lower() == 'y'
    if add_routes:
        while True:
            cidr = input("Enter route CIDR (or leave empty to finish adding routes): ")
            if not cidr:
                break
            
            if validate_cidr(cidr):
                gateway = input(f"Enter gateway for {cidr}: ")
                routes.append({'Cidr': cidr, 'Gateway': gateway})
            else:
                print("Invalid CIDR format. Please try again.")
    
    return create_medialive_network(medialive_client, name, ip_pools, routes if routes else None)

def create_rtmp_input(args, direct_config=None):
    """Create RTMP Push Input based on arguments or direct config"""
    medialive_client = boto3.client('medialive', region_name=args.region)
    
    # Store resource information for reporting
    resource_info = {
        'subnets': [],
        'security_groups': [],
        'availability_zones': {},
        'networks': []
    }
    
    # If direct_config is provided, use it instead of building from args
    if direct_config:
        try:
            response = medialive_client.create_input(**direct_config)
            return response, resource_info
        except ClientError as e:
            print(f"Error creating RTMP input from config: {e}")
            raise
    
    # Otherwise, proceed with args-based configuration
    input_name = validate_name(medialive_client, args.name)
    location = "ON_PREMISES" if args.source_type == "ON_PREMISES" else "AWS"
    
    input_request = {
        'Name': input_name,
        'Type': 'RTMP_PUSH',
        'InputNetworkLocation': location
    }
    
    # Set up destinations if app info provided
    if args.app_name and args.app_instance:
        input_request['Destinations'] = [
            {'StreamName': f"{args.app_name}/{args.app_instance}"},
            {'StreamName': f"{args.secondary_app_name or args.app_name}/{args.secondary_app_instance or args.app_instance}"}
        ]
    
    # Get available resources
    available_subnets, available_security_groups = get_available_resources(args.region)
    
    # Store subnet AZs for reporting
    for subnet in available_subnets:
        resource_info['availability_zones'][subnet['SubnetId']] = subnet.get('AvailabilityZone', 'Unknown')
    
    # Handle source-type specific settings
    if args.source_type == 'AWS':
        # For AWS source type, we need MediaLive InputSecurityGroups (not EC2 security groups)
        ml_security_groups = get_available_security_groups(medialive_client)
        
        # If the user provided a CIDR with --security-group
        if args.security_group and validate_cidr(args.security_group):
            sg_response = medialive_client.create_input_security_group(
                WhitelistRules=[{'Cidr': args.security_group}],
                Tags={'AutoCreated': 'True'}
            )
            sg_id = sg_response['SecurityGroup']['Id']
            input_request['InputSecurityGroups'] = [sg_id]
            resource_info['security_groups'].append({
                'id': sg_id,
                'cidr': args.security_group,
                'auto_created': True
            })
        # If the user provided an existing MediaLive security group ID
        elif args.security_group and args.security_group.startswith('sg-'):
            # Check if it's a valid MediaLive security group
            is_ml_sg = any(sg['Id'] == args.security_group for sg in ml_security_groups)
            if is_ml_sg:
                input_request['InputSecurityGroups'] = [args.security_group]
                resource_info['security_groups'].append({
                    'id': args.security_group,
                    'auto_created': False
                })
            else:
                print(f"Warning: {args.security_group} is not a valid MediaLive security group")
                # Let user choose or create one
                if ml_security_groups:
                    print("\nAvailable MediaLive security groups:")
                    for i, sg in enumerate(ml_security_groups, 1):
                        print(f"{i}. {sg['Id']} - {sg.get('WhitelistRules', [])}") 
                    
                    choice = input("\nSelect a security group number or enter 'new' to create one: ")
                    if choice.lower() == 'new':
                        cidr = input("Enter CIDR to whitelist (e.g., 0.0.0.0/0): ")
                        sg_response = medialive_client.create_input_security_group(
                            WhitelistRules=[{'Cidr': cidr}],
                            Tags={'AutoCreated': 'True'}
                        )
                        sg_id = sg_response['SecurityGroup']['Id']
                    else:
                        sg_idx = int(choice) - 1
                        sg_id = ml_security_groups[sg_idx]['Id']
                    
                    input_request['InputSecurityGroups'] = [sg_id]
                    resource_info['security_groups'].append({
                        'id': sg_id,
                        'auto_created': False  
                    })
                else:
                    # No existing security groups, create one
                    cidr = input("No existing MediaLive security groups. Enter CIDR to whitelist (e.g., 0.0.0.0/0): ")
                    sg_response = medialive_client.create_input_security_group(
                        WhitelistRules=[{'Cidr': cidr}],
                        Tags={'AutoCreated': 'True'}
                    )
                    sg_id = sg_response['SecurityGroup']['Id']
                    input_request['InputSecurityGroups'] = [sg_id]
                    resource_info['security_groups'].append({
                        'id': sg_id,
                        'cidr': cidr,
                        'auto_created': True
                    })
        else:
            # No security group provided, let user select or create one
            if ml_security_groups:
                print("\nAvailable MediaLive security groups:")
                for i, sg in enumerate(ml_security_groups, 1):
                    whitelist = [rule.get('Cidr', 'N/A') for rule in sg.get('WhitelistRules', [])]
                    print(f"{i}. {sg['Id']} - Whitelist: {whitelist}")
                
                choice = input("\nSelect a security group number or enter 'new' to create one: ")
                if choice.lower() == 'new':
                    cidr = input("Enter CIDR to whitelist (e.g., 0.0.0.0/0): ")
                    sg_response = medialive_client.create_input_security_group(
                        WhitelistRules=[{'Cidr': cidr}],
                        Tags={'AutoCreated': 'True'}
                    )
                    sg_id = sg_response['SecurityGroup']['Id']
                else:
                    sg_idx = int(choice) - 1
                    sg_id = ml_security_groups[sg_idx]['Id']
                
                input_request['InputSecurityGroups'] = [sg_id]
                resource_info['security_groups'].append({
                    'id': sg_id,
                    'auto_created': False
                })
            else:
                # No existing security groups, create one
                cidr = input("No existing MediaLive security groups. Enter CIDR to whitelist (e.g., 0.0.0.0/0): ")
                sg_response = medialive_client.create_input_security_group(
                    WhitelistRules=[{'Cidr': cidr}],
                    Tags={'AutoCreated': 'True'}
                )
                sg_id = sg_response['SecurityGroup']['Id']
                input_request['InputSecurityGroups'] = [sg_id]
                resource_info['security_groups'].append({
                    'id': sg_id,
                    'cidr': cidr,
                    'auto_created': True
                })
    
    elif args.source_type == 'AWS_VPC':
        vpc_config = {}
        
        if args.subnets and len(args.subnets) >= 2:
            valid_subnet_ids = [s['SubnetId'] for s in available_subnets]
            valid_subnets = [s for s in args.subnets if s in valid_subnet_ids]
            
            if len(valid_subnets) >= 2:
                vpc_config['SubnetIds'] = valid_subnets[:2]
                resource_info['subnets'] = valid_subnets[:2]
            else:
                print(f"Not enough valid subnets provided. Need at least 2.")
                selected_subnets = select_resources(available_subnets, "subnet", multiple=True, min_count=2)[:2]
                vpc_config['SubnetIds'] = selected_subnets
                resource_info['subnets'] = selected_subnets
        else:
            print("AWS_VPC source type requires at least 2 subnet IDs.")
            selected_subnets = select_resources(available_subnets, "subnet", multiple=True, min_count=2)[:2]
            vpc_config['SubnetIds'] = selected_subnets
            resource_info['subnets'] = selected_subnets
        
        if args.security_group and args.security_group.startswith('sg-'):
            sg_exists = any(sg['GroupId'] == args.security_group for sg in available_security_groups)
            if sg_exists:
                sg_id = args.security_group
                vpc_config['SecurityGroupIds'] = [sg_id]
                sg_info = next((sg for sg in available_security_groups if sg['GroupId'] == sg_id), {})
                resource_info['security_groups'].append({
                    'id': sg_id,
                    'name': sg_info.get('GroupName', 'Unknown'),
                    'description': sg_info.get('Description', '')
                })
            else:
                print(f"Security group {args.security_group} not found.")
                sg_id = select_resources(available_security_groups, "security group")[0]
                vpc_config['SecurityGroupIds'] = [sg_id]
                sg_info = next((sg for sg in available_security_groups if sg['GroupId'] == sg_id), {})
                resource_info['security_groups'].append({
                    'id': sg_id,
                    'name': sg_info.get('GroupName', 'Unknown'),
                    'description': sg_info.get('Description', '')
                })
        
        input_request['Vpc'] = vpc_config
        input_request['RoleArn'] = args.role_arn or input("Enter Role ARN: ")
    
    elif args.source_type == 'ON_PREMISES':
        # Get available networks or create a new one
        available_networks = get_available_networks(medialive_client)
        
        network_id = args.network
        if not network_id:
            if available_networks:
                print("\nAvailable MediaLive networks:")
                for i, network in enumerate(available_networks, 1):
                    print(f"{i}. {network['Id']} - {network.get('Name', 'N/A')}")
                
                choice = input("\nSelect a network number or enter 'new' to create one: ")
                if choice.lower() == 'new':
                    # Create new network
                    network_id = create_new_network(medialive_client)
                else:
                    network_idx = int(choice) - 1
                    network_id = available_networks[network_idx]['Id']
            else:
                print("No existing networks found. Creating a new network.")
                network_id = create_new_network(medialive_client)
        
        if not network_id:
            raise ValueError("Network ID is required for ON_PREMISES source type")
        
        # Store network info for reporting
        resource_info['networks'].append(network_id)
        
        for dest in input_request.get('Destinations', []):
            dest['Network'] = network_id
            
            if args.static_ip:
                dest['StaticIpAddress'] = args.static_ip
            if args.network_routes:
                dest['NetworkRoutes'] = [
                    {'Cidr': r.split(':', 1)[0], 'Gateway': r.split(':', 1)[1]} if ':' in r 
                    else {'Cidr': r} for r in args.network_routes
                ]
    
    # Add tags
    if args.tags:
        input_request['Tags'] = {k: v for tag in args.tags for k, v in [tag.split('=', 1)] if '=' in tag}
    
    try:
        response = medialive_client.create_input(**input_request)
        return response, resource_info
    except ClientError as e:
        print(f"Error creating RTMP input: {e}")
        raise

def parse_arguments():
    parser = argparse.ArgumentParser(description='Create AWS MediaLive RTMP Push Input')    
    parser.add_argument('--config', type=str, help='Path to JSON configuration file')
    parser.add_argument('--name', type=str, help='Name for the RTMP input (optional)')
    parser.add_argument('--app-name', type=str, help='Application name')
    parser.add_argument('--app-instance', type=str, help='Application instance')
    parser.add_argument('--secondary-app-name', type=str, help='Secondary application name')
    parser.add_argument('--secondary-app-instance', type=str, help='Secondary application instance')
    parser.add_argument('--source-type', type=str, choices=['AWS', 'AWS_VPC', 'ON_PREMISES'])
    parser.add_argument('--security-group', type=str, help='Security group ID, name, or CIDR')
    parser.add_argument('--subnets', type=str, nargs='+', help='Subnet IDs for AWS_VPC')
    parser.add_argument('--role-arn', type=str, help='Role ARN for AWS_VPC')
    parser.add_argument('--network', type=str, help='Network ID for ON_PREMISES')
    parser.add_argument('--static-ip', type=str, help='Static IP for ON_PREMISES')
    parser.add_argument('--network-routes', type=str, nargs='+', help='Routes (CIDR:gateway)')
    parser.add_argument('--tags', type=str, nargs='+', help='Tags (Key=Value)')
    parser.add_argument('--region', type=str, default='us-east-2', help='AWS region')
    return parser.parse_args()
  
def main():
    try:
        args = parse_arguments()
        
        # Check if using config file
        direct_config = None
        if args.config:
            direct_config = load_config_file(args.config)
            if not hasattr(args, 'region') or not args.region:
                args.region = direct_config.get('region', 'us-west-2')
            print(f"Using configuration from {args.config}")
        else:
            # Validate basic required args
            if not args.source_type:
                print("Error: --source-type is required when not using config file")
                return 1
            if not args.app_name or not args.app_instance:
                print("Error: --app-name and --app-instance are required when not using config file")
                return 1
  
        response, resource_info = create_rtmp_input(args, direct_config)
        
        print(json.dumps(response, indent=2, default=str)) # JSON pass through
        print("\nRTMP Input created successfully!")
        
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
