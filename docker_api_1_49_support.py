#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker API v1.49 Support Module (Docker 25.0.x)

This module adds support for the latest Docker API features, including:
1. BuildKit build progress events
2. Registry search enhancements
3. Multi-platform images in resource listings
4. Enhanced image buildinfo
"""

import json
import logging
import re
from typing import Dict, List, Any, Tuple, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DockerApi149Support:
    """Helper class for Docker API v1.49 specific features"""
    
    @staticmethod
    def is_api_149_supported(api_version: str) -> bool:
        """
        Check if API version is 1.49 or higher
        
        Args:
            api_version (str): Docker API version string
            
        Returns:
            bool: True if API version 1.49+ is supported
        """
        if not api_version:
            return False
            
        # Remove 'v' prefix if present
        if api_version.startswith('v'):
            api_version = api_version[1:]
            
        # Split into major.minor
        try:
            major, minor = map(int, api_version.split('.', 1))
            return (major > 1) or (major == 1 and minor >= 49)
        except (ValueError, IndexError):
            return False
    
    @staticmethod
    def get_buildkit_progress_command(tag: str, context_path: str, 
                                      build_args: Dict[str, str] = None,
                                      platforms: List[str] = None) -> str:
        """
        Generate a Docker build command with progress reporting
        
        Args:
            tag (str): Image tag
            context_path (str): Build context path
            build_args (dict): Build arguments as key-value pairs
            platforms (list): List of platforms to build for
            
        Returns:
            str: Docker build command
        """
        cmd = "docker buildx build --progress=plain"
        
        # Add build arguments
        if build_args:
            for key, value in build_args.items():
                cmd += f" --build-arg {key}={value}"
        
        # Add platforms
        if platforms:
            platform_str = ','.join(platforms)
            cmd += f" --platform={platform_str}"
        
        # Add tag and context
        cmd += f" -t {tag} {context_path}"
        
        return cmd
    
    @staticmethod
    def parse_buildkit_progress(output: str) -> Dict[str, Any]:
        """
        Parse BuildKit progress output into structured data
        
        Args:
            output (str): Raw BuildKit progress output
            
        Returns:
            dict: Structured build progress data
        """
        stages = {}
        current_stage = None
        
        # Regular expressions for parsing
        stage_start = re.compile(r'#(\d+) \[([^\]]+)\]')
        progress_line = re.compile(r'#\d+ (\d+\.\d+) (.+)')
        
        for line in output.split('\n'):
            line = line.strip()
            
            # Check for stage markers
            stage_match = stage_start.match(line)
            if stage_match:
                stage_num, stage_name = stage_match.groups()
                current_stage = stage_name
                if current_stage not in stages:
                    stages[current_stage] = {
                        'steps': [],
                        'status': 'in_progress'
                    }
                continue
            
            # Check for progress updates
            progress_match = progress_line.match(line)
            if progress_match and current_stage:
                progress, msg = progress_match.groups()
                stages[current_stage]['steps'].append({
                    'progress': float(progress),
                    'message': msg,
                    'timestamp': None  # Would be set in real implementation
                })
                continue
            
            # Check for completion markers
            if line.startswith('Successfully built') and current_stage:
                stages[current_stage]['status'] = 'completed'
            
            # Check for error markers
            if line.startswith('ERROR') and current_stage:
                stages[current_stage]['status'] = 'failed'
                stages[current_stage]['error'] = line
        
        return {
            'stages': stages,
            'completed': all(s['status'] == 'completed' for s in stages.values()),
            'failed': any(s['status'] == 'failed' for s in stages.values())
        }
    
    @staticmethod
    def enhanced_registry_search(ssh_client, search_term: str, 
                                 filters: Dict[str, str] = None, 
                                 limit: int = None, 
                                 use_sudo: bool = False) -> List[Dict[str, Any]]:
        """
        Perform enhanced registry search with filtering
        
        Args:
            ssh_client: SSH client instance
            search_term (str): Search term
            filters (dict): Filters to apply (is-official, is-automated, stars)
            limit (int): Maximum number of results
            use_sudo (bool): Whether to use sudo
            
        Returns:
            list: Search results
        """
        cmd = f"docker search --format '{{{{json .}}}}'"
        
        # Add filters
        if filters:
            for key, value in filters.items():
                cmd += f" --filter {key}={value}"
        
        # Add limit
        if limit:
            cmd += f" --limit {limit}"
        
        # Add search term
        cmd += f" {search_term}"
        
        # Add sudo if needed
        if use_sudo:
            cmd = f"sudo {cmd}"
        
        # Execute the command
        output = ssh_client.execute_command(cmd)
        
        # Parse the JSON results (one per line)
        results = []
        for line in output.strip().split('\n'):
            if line:
                try:
                    result = json.loads(line)
                    results.append(result)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse search result: {line}")
        
        return results
    
    @staticmethod
    def get_multiplatform_images(ssh_client, use_sudo: bool = False) -> List[Dict[str, Any]]:
        """
        Get list of multi-platform images
        
        Args:
            ssh_client: SSH client instance
            use_sudo (bool): Whether to use sudo
            
        Returns:
            list: Multi-platform image details
        """
        cmd = "docker images --format '{{json .}}'"
        
        # Add sudo if needed
        if use_sudo:
            cmd = f"sudo {cmd}"
        
        # Execute the command
        output = ssh_client.execute_command(cmd)
        
        # Parse and filter for multi-platform images
        multiplatform_images = []
        for line in output.strip().split('\n'):
            if line:
                try:
                    image = json.loads(line)
                    # Check if it has platform info
                    if 'Platform' in image and image['Platform']:
                        multiplatform_images.append(image)
                except json.JSONDecodeError:
                    continue
        
        return multiplatform_images
    
    @staticmethod
    def get_build_info(ssh_client, image_id: str, use_sudo: bool = False) -> Dict[str, Any]:
        """
        Get enhanced build info for an image
        
        Args:
            ssh_client: SSH client instance
            image_id (str): Image ID or name
            use_sudo (bool): Whether to use sudo
            
        Returns:
            dict: Build information
        """
        cmd = f"docker image inspect --format '{{{{json .}}}}' {image_id}"
        
        # Add sudo if needed
        if use_sudo:
            cmd = f"sudo {cmd}"
        
        # Execute the command
        output = ssh_client.execute_command(cmd)
        
        try:
            # Parse the JSON output
            image_data = json.loads(output.strip())
            
            # Extract build info
            if isinstance(image_data, list):
                image_data = image_data[0]
            
            build_info = {
                'Id': image_data.get('Id', ''),
                'Created': image_data.get('Created', ''),
                'Architecture': image_data.get('Architecture', ''),
                'Os': image_data.get('Os', ''),
                'Size': image_data.get('Size', 0),
                'BuildInfo': {}
            }
            
            # Extract detailed build info if available
            if 'Config' in image_data and 'Labels' in image_data['Config']:
                labels = image_data['Config']['Labels'] or {}
                
                # BuildKit labels
                buildkit_labels = {k: v for k, v in labels.items() if k.startswith('com.docker.buildkit')}
                if buildkit_labels:
                    build_info['BuildInfo']['BuildKit'] = buildkit_labels
                
                # General build labels
                build_labels = {k: v for k, v in labels.items() if 'build' in k.lower()}
                if build_labels:
                    build_info['BuildInfo']['Labels'] = build_labels
            
            # Extract history for build stages
            if 'History' in image_data:
                build_info['BuildInfo']['History'] = image_data['History']
            
            return build_info
            
        except json.JSONDecodeError:
            logger.error(f"Failed to parse image inspect output: {output}")
            return {}

    @staticmethod
    def get_api_features(api_version: str) -> Dict[str, Any]:
        """
        Get available API features for the given version
        
        Args:
            api_version (str): Docker API version
            
        Returns:
            dict: API features and their availability
        """
        features = {
            'BuildKit build progress': {
                'available': DockerApi149Support.is_api_149_supported(api_version),
                'min_version': '1.49',
                'description': 'Detailed build progress events from BuildKit',
                'example': 'docker build --progress=plain -t test .'
            },
            'Registry search enhancements': {
                'available': DockerApi149Support.is_api_149_supported(api_version),
                'min_version': '1.49',
                'description': 'Enhanced registry search with additional filters',
                'example': 'docker search --filter is-official=true ubuntu'
            },
            'Multi-platform image listing': {
                'available': DockerApi149Support.is_api_149_supported(api_version),
                'min_version': '1.49',
                'description': 'Platform information in image listings',
                'example': "docker images --format '{{json .}}' | jq 'select(.Platform != null)'"
            },
            'Enhanced build info': {
                'available': DockerApi149Support.is_api_149_supported(api_version),
                'min_version': '1.49',
                'description': 'Detailed build information for images',
                'example': 'docker buildx build --build-arg VERSION=latest --platform=linux/amd64,linux/arm64 .'
            }
        }
        
        # Add overall support status
        features['_support_status'] = {
            'version': api_version,
            'api_1_49_supported': DockerApi149Support.is_api_149_supported(api_version),
            'supported_features': sum(1 for f in features.values() if isinstance(f, dict) and f.get('available', False)),
            'total_features': sum(1 for f in features.values() if isinstance(f, dict))
        }
        
        return features

    @staticmethod
    def generate_api_version_html(api_version: str) -> str:
        """
        Generate HTML output for API version information
        
        Args:
            api_version (str): Docker API version
            
        Returns:
            str: HTML formatted API version information
        """
        features = DockerApi149Support.get_api_features(api_version)
        support_status = features.pop('_support_status')
        
        # Start with the header
        is_v149 = DockerApi149Support.is_api_149_supported(api_version)
        version_class = "text-success" if is_v149 else "text-warning"
        
        html = f"""
        <div class="mt-3">
            <div class="alert alert-info" role="alert">
                <strong>Docker Engine Version:</strong> {api_version} 
                <span class="{version_class}">
                    ({support_status['supported_features']}/{support_status['total_features']} API 1.49 features supported)
                </span>
            </div>
            
            <h4 class="mt-4">API Features</h4>
            <ul>
        """
        
        # Add feature list
        for name, feature in features.items():
            status_class = "text-success" if feature.get('available') else "text-muted"
            html += f"""
                <li class="{status_class}">{name}</li>
            """
        
        html += """
            </ul>
            
            <h4 class="mt-4">Compatibility Notes</h4>
            <p>Image build events now support detailed progress reporting from BuildKit.</p>
            
            <h4 class="mt-4">Example Commands</h4>
        """
        
        # Add example commands
        for name, feature in features.items():
            cmd_example = feature.get('example', '')
            if cmd_example:
                cmd_name = name.lower().replace(' ', '_')
                html += f"""
                <div class="mb-3"><strong>{cmd_name}:</strong>
                    <pre class="bg-light p-2 mt-1"><code>{cmd_example}</code></pre>
                </div>
                """
        
        html += """
        </div>
        """
        
        return html

# Example usage
if __name__ == "__main__":
    # This module would be used like:
    """
    from docker_api_1_49_support import DockerApi149Support
    
    # Check if API version is supported
    if DockerApi149Support.is_api_149_supported(server.api_version):
        # Use enhanced features
        multiplatform_images = DockerApi149Support.get_multiplatform_images(ssh_client)
        build_info = DockerApi149Support.get_build_info(ssh_client, "image_id")
        
    # Generate HTML information for API version
    api_html = DockerApi149Support.generate_api_version_html(server.api_version)
    """
    
    # Test with a sample API version
    sample_version = "1.49"
    features = DockerApi149Support.get_api_features(sample_version)
    print(f"API version {sample_version} features:")
    for name, feature in features.items():
        if isinstance(feature, dict) and name != "_support_status":
            status = "Available" if feature.get('available') else "Not available"
            print(f"- {name}: {status}")
    
    # Generate sample HTML
    html = DockerApi149Support.generate_api_version_html(sample_version)
    print("\nAPI version HTML preview (first 500 chars):")
    print(html[:500] + "...")