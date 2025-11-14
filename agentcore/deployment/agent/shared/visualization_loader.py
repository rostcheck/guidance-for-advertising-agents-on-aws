"""
Programmatic visualization loader for AgentCore agents.
Loads visualization maps and template data without relying on file_read tools.
"""

import os
import json
from typing import Dict, List, Optional, Any


class VisualizationLoader:
    """Load visualization configurations programmatically for agents."""
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize the visualization loader.
        
        Args:
            base_dir: Base directory for visualization library. 
                     Defaults to agent-visualizations-library in the same directory as handler.py
        """
        if base_dir is None:
            # Default to the agent-visualizations-library directory
            handler_dir = os.path.dirname(os.path.dirname(__file__))
            self.base_dir = os.path.join(handler_dir, "agent-visualizations-library")
        else:
            self.base_dir = base_dir
            
        self.maps_dir = os.path.join(self.base_dir, "agent-visualization-maps")
    
    def load_agent_visualization_map(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        Load the visualization map for a specific agent.
        
        Args:
            agent_name: Name of the agent (e.g., "AdLoadOptimizationAgent")
            
        Returns:
            Dictionary containing agent visualization map, or None if not found
        """
        map_path = os.path.join(self.maps_dir, f"{agent_name}.json")
        
        if not os.path.exists(map_path):
            print(f"[VisualizationLoader] Warning: No visualization map found for {agent_name} at {map_path}")
            return None
        
        try:
            with open(map_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[VisualizationLoader] Error loading visualization map for {agent_name}: {e}")
            return None
    
    def load_template_data(self, agent_name: str, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Load the data mapping for a specific agent template.
        
        Args:
            agent_name: Name of the agent (e.g., "AdLoadOptimizationAgent")
            template_id: Template ID (e.g., "metrics-visualization")
            
        Returns:
            Dictionary containing the dataMapping field, or None if not found
        """
        template_path = os.path.join(self.base_dir, f"{agent_name}-{template_id}.json")
        
        if not os.path.exists(template_path):
            print(f"[VisualizationLoader] Warning: No template data found for {agent_name}/{template_id} at {template_path}")
            return None
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Return the dataMapping field
                return data.get("dataMapping")
        except Exception as e:
            print(f"[VisualizationLoader] Error loading template data for {agent_name}/{template_id}: {e}")
            return None
    
    def load_all_templates_for_agent(self, agent_name: str) -> Dict[str, Dict[str, Any]]:
        """
        Load all visualization templates for a specific agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Dictionary mapping template_id to dataMapping content
        """
        # First load the agent's visualization map
        viz_map = self.load_agent_visualization_map(agent_name)
        
        if not viz_map:
            return {}
        
        templates = viz_map.get("templates", [])
        result = {}
        
        for template in templates:
            template_id = template.get("templateId")
            if template_id:
                data_mapping = self.load_template_data(agent_name, template_id)
                if data_mapping:
                    result[template_id] = {
                        "usage": template.get("usage", ""),
                        "dataMapping": data_mapping
                    }
        
        return result
    
    def get_visualization_instructions(self, agent_name: str) -> str:
        """
        Generate instructions for an agent on how to use its visualizations.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Formatted instruction string for the agent
        """
        viz_map = self.load_agent_visualization_map(agent_name)
        
        if not viz_map:
            return f"No visualizations configured for {agent_name}."
        
        templates = viz_map.get("templates", [])
        
        if not templates:
            return f"No visualization templates available for {agent_name}."
        
        instructions = [
            f"\n## Available Visualizations for {agent_name}\n",
            "You have access to the following visualization templates:\n"
        ]
        
        for template in templates:
            template_id = template.get("templateId")
            usage = template.get("usage", "No description")
            instructions.append(f"- **{template_id}**: {usage}")
        
        instructions.append("\n## How to Use Visualizations\n")
        instructions.append("1. Determine which template best fits your analysis")
        instructions.append("2. Load the template data mapping programmatically")
        instructions.append("3. Map your analysis results to the template fields")
        instructions.append("4. Wrap the result in XML: <visualization-data type='[template-id]'>[JSON_RESULT]</visualization-data>\n")
        
        return "\n".join(instructions)
    
    def get_template_structure(self, agent_name: str, template_id: str) -> Optional[str]:
        """
        Get a formatted string showing the structure of a template.
        
        Args:
            agent_name: Name of the agent
            template_id: Template ID
            
        Returns:
            Formatted JSON string showing template structure, or None if not found
        """
        data_mapping = self.load_template_data(agent_name, template_id)
        
        if not data_mapping:
            return None
        
        return json.dumps(data_mapping, indent=2)


# Convenience function for quick access
def load_visualizations_for_agent(agent_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Quick helper to load all visualizations for an agent.
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary mapping template_id to template data
    """
    loader = VisualizationLoader()
    return loader.load_all_templates_for_agent(agent_name)


def get_visualization_prompt_addition(agent_name: str) -> str:
    """
    Get prompt addition text for visualization instructions.
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Formatted instruction text to add to agent prompt
    """
    loader = VisualizationLoader()
    return loader.get_visualization_instructions(agent_name)


# Example usage in handler.py:
# from shared.visualization_loader import VisualizationLoader
# 
# loader = VisualizationLoader()
# templates = loader.load_all_templates_for_agent("AdLoadOptimizationAgent")
# 
# # Access specific template
# metrics_template = templates.get("metrics-visualization", {}).get("dataMapping")
