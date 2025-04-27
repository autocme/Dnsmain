#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Example script demonstrating how to use the Paramiko SSH client to interact with remote Docker servers
This script shows how to retrieve, parse, and process Docker information from remote servers
"""

import json
import sys
import argparse
from paramiko_ssh_client import ParamikoSshClient

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Docker SSH Client Example")
    
    # Connection parameters
    parser.add_argument('--host', required=True, help="SSH server hostname or IP")
    parser.add_argument('--port', type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument('--user', required=True, help="SSH username")
    parser.add_argument('--password', help="SSH password (prefer key auth)")
    parser.add_argument('--key-file', help="Path to private key file")
    
    # Actions
    parser.add_argument('--action', choices=['info', 'list-containers', 'list-images', 'stats'],
                        default='info', help="Action to perform")
    
    return parser.parse_args()

def get_docker_info(ssh_client):
    """Get Docker server information"""
    print("Retrieving Docker server information...")
    
    # Use --format to get JSON output for easier parsing
    output = ssh_client.execute_command("docker info --format '{{json .}}'")
    
    try:
        # Parse the JSON output
        info = json.loads(output)
        
        # Print nicely formatted information
        print("\nDocker Server Information:")
        print(f"Server Version:  {info.get('ServerVersion', 'Unknown')}")
        print(f"Containers:      {info.get('Containers', 0)} (Running: {info.get('ContainersRunning', 0)}, Paused: {info.get('ContainersPaused', 0)}, Stopped: {info.get('ContainersStopped', 0)})")
        print(f"Images:          {info.get('Images', 0)}")
        print(f"Operating System: {info.get('OperatingSystem', 'Unknown')}")
        print(f"Architecture:    {info.get('Architecture', 'Unknown')}")
        print(f"Kernel Version:  {info.get('KernelVersion', 'Unknown')}")
        
        # Print driver information
        print(f"\nStorage Driver:  {info.get('Driver', 'Unknown')}")
        print(f"Logging Driver:  {info.get('LoggingDriver', 'Unknown')}")
        
        # Print plugins if available
        if 'Plugins' in info:
            plugins = info['Plugins']
            print("\nPlugins:")
            
            if 'Volume' in plugins:
                print(f"  Volume:         {', '.join(plugins['Volume'])}")
            if 'Network' in plugins:
                print(f"  Network:        {', '.join(plugins['Network'])}")
            
        return info
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output: {str(e)}")
        print(f"Raw output: {output}")
        return None

def list_containers(ssh_client):
    """List Docker containers"""
    print("Listing Docker containers...")
    
    # Use --format to get JSON output for easier parsing
    output = ssh_client.execute_command("docker ps -a --format '{{json .}}'")
    
    # Split by newline to get each container JSON object
    container_jsons = [line for line in output.split('\n') if line.strip()]
    
    if not container_jsons:
        print("No containers found.")
        return []
    
    containers = []
    print("\nContainers:")
    print(f"{'CONTAINER ID':<15} {'IMAGE':<30} {'STATUS':<20} {'NAMES':<20}")
    print("-" * 85)
    
    for container_json in container_jsons:
        try:
            container = json.loads(container_json)
            containers.append(container)
            
            # Extract and print relevant information
            container_id = container.get('ID', 'Unknown')[:12]
            image = container.get('Image', 'Unknown')
            status = container.get('Status', 'Unknown')
            name = container.get('Names', 'Unknown')
            
            print(f"{container_id:<15} {image:<30} {status:<20} {name:<20}")
        except json.JSONDecodeError as e:
            print(f"Error parsing container: {str(e)}")
    
    return containers

def list_images(ssh_client):
    """List Docker images"""
    print("Listing Docker images...")
    
    # Use --format to get JSON output for easier parsing
    output = ssh_client.execute_command("docker images --format '{{json .}}'")
    
    # Split by newline to get each image JSON object
    image_jsons = [line for line in output.split('\n') if line.strip()]
    
    if not image_jsons:
        print("No images found.")
        return []
    
    images = []
    print("\nImages:")
    print(f"{'REPOSITORY':<40} {'TAG':<20} {'IMAGE ID':<15} {'SIZE':<10}")
    print("-" * 85)
    
    for image_json in image_jsons:
        try:
            image = json.loads(image_json)
            images.append(image)
            
            # Extract and print relevant information
            repository = image.get('Repository', 'Unknown')
            tag = image.get('Tag', 'Unknown')
            image_id = image.get('ID', 'Unknown')[:12]
            size = image.get('Size', 'Unknown')
            
            print(f"{repository:<40} {tag:<20} {image_id:<15} {size:<10}")
        except json.JSONDecodeError as e:
            print(f"Error parsing image: {str(e)}")
    
    return images

def get_docker_stats(ssh_client):
    """Get Docker container statistics"""
    print("Retrieving Docker container statistics...")
    
    # Use --no-stream to get a snapshot rather than continuous updates
    # And --format for JSON output
    output = ssh_client.execute_command("docker stats --no-stream --format '{{json .}}'")
    
    # Split by newline to get each container stats JSON object
    stats_jsons = [line for line in output.split('\n') if line.strip()]
    
    if not stats_jsons:
        print("No running containers found.")
        return []
    
    stats = []
    print("\nContainer Statistics:")
    print(f"{'CONTAINER ID':<15} {'NAME':<30} {'CPU %':<10} {'MEM USAGE / LIMIT':<30} {'MEM %':<10} {'NET I/O':<20} {'BLOCK I/O':<20}")
    print("-" * 135)
    
    for stats_json in stats_jsons:
        try:
            container_stats = json.loads(stats_json)
            stats.append(container_stats)
            
            # Extract and print relevant information
            container_id = container_stats.get('ID', 'Unknown')[:12]
            name = container_stats.get('Name', 'Unknown')
            cpu = container_stats.get('CPUPerc', 'Unknown')
            mem_usage = container_stats.get('MemUsage', 'Unknown')
            mem_perc = container_stats.get('MemPerc', 'Unknown')
            net_io = container_stats.get('NetIO', 'Unknown')
            block_io = container_stats.get('BlockIO', 'Unknown')
            
            print(f"{container_id:<15} {name:<30} {cpu:<10} {mem_usage:<30} {mem_perc:<10} {net_io:<20} {block_io:<20}")
        except json.JSONDecodeError as e:
            print(f"Error parsing container stats: {str(e)}")
    
    return stats

def main():
    """Main entry point"""
    args = parse_arguments()
    
    # Create SSH client
    ssh_client = ParamikoSshClient(
        hostname=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        key_file=args.key_file,
        use_clean_output=True,  # Always use clean output for JSON parsing
        force_minimal_terminal=True  # Always use minimal terminal to prevent ANSI codes
    )
    
    # Connect to the server
    if not ssh_client.connect():
        print("Failed to connect to the server.")
        return 1
    
    try:
        # Perform the requested action
        if args.action == 'info':
            get_docker_info(ssh_client)
        elif args.action == 'list-containers':
            list_containers(ssh_client)
        elif args.action == 'list-images':
            list_images(ssh_client)
        elif args.action == 'stats':
            get_docker_stats(ssh_client)
    finally:
        # Disconnect
        ssh_client.disconnect()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())