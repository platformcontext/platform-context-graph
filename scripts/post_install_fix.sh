#!/bin/bash
set -e

echo "Running Post Install fix for PlatformContextGraph..."

detect_shell_config() {
    # Windows PowerShell detection
    if [[ "$OS" == "Windows_NT" ]] && [[ -n "$PROFILE" ]]; then
        echo "$PROFILE"
        return
    fi
    
    # Unix/Linux/Mac shell detection
    if [ "$SHELL" = "/bin/bash" ] || [ "$SHELL" = "/usr/bin/bash" ]; then
        echo "$HOME/.bashrc"
    elif [ "$SHELL" = "/bin/zsh" ] || [ "$SHELL" = "/usr/bin/zsh" ]; then
        echo "$HOME/.zshrc"
    elif [ -n "$BASH_VERSION" ]; then
        echo "$HOME/.bashrc"
    elif [ -n "$ZSH_VERSION" ]; then
        echo "$HOME/.zshrc"
    else
        echo "$HOME/.profile"
    fi
}

# Add to PATH for Windows PowerShell
fix_windows_path() {
    local profile_file="$1"
    local path_line='$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"'
    
    echo "Using PowerShell profile: $profile_file"
    
    # Create profile directory if needed
    local profile_dir=$(dirname "$profile_file")
    mkdir -p "$profile_dir" 2>/dev/null || true
    
    # Check if already configured
    if [[ -f "$profile_file" ]] && grep -q ".local" "$profile_file"; then
        echo "PATH is already configured in PowerShell profile"
    else
        echo "Adding to PowerShell PATH..."
        echo "" >> "$profile_file"
        echo "# Added by PlatformContextGraph" >> "$profile_file"
        echo "$path_line" >> "$profile_file"
        echo "Added PATH to PowerShell profile"
    fi
    
    # Add to current session (Windows style)
    export PATH="$USERPROFILE/.local/bin:$PATH"
    
    echo "⚠️ Please restart PowerShell or run: . \$PROFILE"
}

# Add to PATH for Linux/Mac
fix_unix_path() {
    local config_file="$1"
    local path_line='export PATH="$HOME/.local/bin:$PATH"'

    echo "Using shell config: $config_file"

    # check if PATH is already configured
    if [ -f "$config_file" ] && grep -q ".local/bin" "$config_file"; then
        echo "PATH is already configured in $config_file"
    else
        echo "Adding ~/.local/bin to PATH..."
        echo "" >> "$config_file"
        echo "# Added by PlatformContextGraph" >> "$config_file"
        echo "$path_line" >> "$config_file"
        echo "Added PATH to $config_file"
    fi

    # Source the config for current session
    echo "Sourcing/Reloading shell config for current session..."
    export PATH="$HOME/.local/bin:$PATH"

    # source it 
    if [ -f "$config_file" ]; then
        source "$config_file" 2>/dev/null || true
    fi
}

# Main PATH fixing function
fix_path() {
    local config_file=$(detect_shell_config)
    
    # Check if we're on Windows
    if [[ "$OS" == "Windows_NT" ]] && [[ -n "$PROFILE" ]]; then
        fix_windows_path "$config_file"
    else
        fix_unix_path "$config_file"
    fi
}

check_pcg() {
    if command -v pcg >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Get potential pcg locations based on platform
get_pcg_locations() {
    if [[ "$OS" == "Windows_NT" ]]; then
        # Windows locations
        echo "$USERPROFILE/.local/bin/pcg.exe"
        echo "$USERPROFILE/.local/bin/pcg"
        echo "$HOME/.local/bin/pcg.exe"
        echo "$HOME/.local/bin/pcg"
    else
        # Linux/Mac locations
        echo "$HOME/.local/bin/pcg"
    fi
}


# Main execution
if check_pcg; then
    echo "✅ pcg (PlatformContextGraph) is already available!"
else
    echo "⚠️ pcg command not found, fixing PATH..."

    # Check if pcg exists in expected locations
    pcg_found=false
    for pcg_path in $(get_pcg_locations); do
        if [[ -f "$pcg_path" ]]; then
            pcg_found=true
            echo "📍 Found pcg at: $pcg_path"
            break
        fi
    done

    if [[ "$pcg_found" == true ]]; then
        fix_path

        # Check again
        if check_pcg; then
            echo "✅ pcg command (PlatformContextGraph) is now available to use!"
            echo "You can now run: pcg neo4j setup"
        else
            if [[ "$OS" == "Windows_NT" ]]; then
                echo "⚠️ Please restart PowerShell or run: . \$PROFILE"
            else
                echo "❌ There seems to still be an issue... Please reload your terminal manually."
            fi
        fi
    else
        if [[ "$OS" == "Windows_NT" ]]; then
            echo "❌ pcg not found in expected Windows locations. Please reinstall:"
            echo "   pip install platform-context-graph"
        else
            echo "❌ pcg not found in ~/.local/bin. Please reinstall:"
            echo "   pip install platform-context-graph"
        fi
    fi
fi