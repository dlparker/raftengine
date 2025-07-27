#!/usr/bin/env python3

import json
import sys
from datetime import datetime

def extract_user_prompts(jsonl_file):
    prompts = []
    
    with open(jsonl_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                
                # Check if this is a user message
                if data.get('type') == 'user':
                    message = data.get('message', {})
                    content = message.get('content')
                    timestamp = data.get('timestamp', '')
                    
                    # Handle different content formats
                    if isinstance(content, str):
                        # Simple string content
                        prompts.append({
                            'timestamp': timestamp,
                            'content': content,
                            'line_num': line_num
                        })
                    elif isinstance(content, list):
                        # List content - look for tool results vs actual user prompts
                        has_tool_result = any(item.get('type') == 'tool_result' for item in content if isinstance(item, dict))
                        if not has_tool_result:
                            # This appears to be actual user content
                            text_content = []
                            for item in content:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    text_content.append(item.get('text', ''))
                            if text_content:
                                prompts.append({
                                    'timestamp': timestamp,
                                    'content': '\n'.join(text_content),
                                    'line_num': line_num
                                })
                        
            except json.JSONDecodeError as e:
                print(f"Error parsing line {line_num}: {e}", file=sys.stderr)
                continue
    
    return prompts

def main():
    jsonl_file = '/home/dparker/projects/lsfs_exp/f3087070-6517-4f11-aee0-8363b014a258.jsonl'
    prompts = extract_user_prompts(jsonl_file)
    
    print(f"Found {len(prompts)} user prompts")
    
    # Create markdown file
    markdown_content = ["# User Prompts from Claude Session", ""]
    markdown_content.append(f"Extracted on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    markdown_content.append(f"Source file: {jsonl_file}")
    markdown_content.append(f"Total prompts: {len(prompts)}")
    markdown_content.append("")
    
    for i, prompt in enumerate(prompts, 1):
        timestamp = prompt['timestamp']
        if timestamp:
            # Parse ISO timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                formatted_time = timestamp
        else:
            formatted_time = "Unknown"
            
        markdown_content.append(f"## Prompt {i}")
        markdown_content.append(f"**Time:** {formatted_time}")
        markdown_content.append(f"**Line:** {prompt['line_num']}")
        markdown_content.append("")
        markdown_content.append("```")
        markdown_content.append(prompt['content'])
        markdown_content.append("```")
        markdown_content.append("")
    
    # Write markdown file
    with open('/home/dparker/projects/lsfs_exp/user_prompts.md', 'w') as f:
        f.write('\n'.join(markdown_content))
    
    # Create marker file for future extractions
    marker_data = {
        'last_extracted': datetime.now().isoformat(),
        'source_file': jsonl_file,
        'total_lines_processed': len(prompts),
        'last_line_processed': prompts[-1]['line_num'] if prompts else 0
    }
    
    with open('/home/dparker/projects/lsfs_exp/extraction_marker.json', 'w') as f:
        json.dump(marker_data, f, indent=2)
    
    print(f"Saved {len(prompts)} prompts to user_prompts.md")
    print(f"Created extraction marker in extraction_marker.json")

if __name__ == "__main__":
    main()