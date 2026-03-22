# 🔍 Troubleshooting: "Index Current Workspace" Failed

## Quick Fix Steps

### Step 1: Reinstall the Extension

The extension has been updated with virtual environment support. You need to reinstall it:

```bash
# Navigate to the extension directory
cd /path/to/PlatformContextGraph/vscode-extension

# Uninstall the old version (if installed)
code --uninstall-extension platformcontext.platform-context-graph

# Install the new version
code --install-extension platform-context-graph-0.1.0.vsix

# Reload VS Code
# Press Cmd+Shift+P → "Developer: Reload Window"
```

### Step 2: Verify pcg is Detected

After reloading VS Code:

1. Open the **Output** panel: `View → Output`
2. Select **"PlatformContextGraph"** from the dropdown
3. Look for a message like:
   ```
   Found pcg in virtual environment: /path/to/PlatformContextGraph/.venv/bin/pcg
   ```

### Step 3: Try Indexing Again

1. Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
2. Type "PCG: Index Current Workspace"
3. Press Enter

## Debugging Steps

### Check 1: Is pcg Working?

Test pcg directly:

```bash
cd /path/to/PlatformContextGraph
.venv/bin/pcg --version
# Should output: PlatformContextGraph 0.2.0
```

### Check 2: Is the Extension Finding pcg?

Check the VS Code Output panel:

1. `View → Output`
2. Select "PlatformContextGraph" from dropdown
3. Look for messages about pcg path

### Check 3: Manual Path Configuration

If auto-detection isn't working, set the path manually:

1. Open VS Code Settings: `Cmd+,` or `Ctrl+,`
2. Search for "pcg.cliPath"
3. Set to: `/path/to/PlatformContextGraph/.venv/bin/pcg`
4. Reload window: `Cmd+Shift+P` → "Developer: Reload Window"

### Check 4: Test pcg Command Manually

Try running the index command manually to see the actual error:

```bash
cd /path/to/PlatformContextGraph
.venv/bin/pcg index /path/to/PlatformContextGraph
```

If this works, the issue is with the extension. If it fails, the issue is with pcg itself.

## Common Issues

### Issue 1: "spawn pcg ENOENT"

**Cause**: Extension can't find pcg executable

**Solutions**:
1. Reinstall the extension (see Step 1 above)
2. Set `pcg.cliPath` manually in settings
3. Check that `.venv/bin/pcg` exists and is executable:
   ```bash
   ls -la .venv/bin/pcg
   chmod +x .venv/bin/pcg  # If needed
   ```

### Issue 2: "PCG command failed"

**Cause**: pcg found but command failed

**Solutions**:
1. Check the Output panel for the actual error message
2. Try running pcg manually to see the error:
   ```bash
   .venv/bin/pcg index .
   ```
3. Check database is accessible:
   ```bash
   .venv/bin/pcg list
   ```

### Issue 3: Extension Not Loading

**Cause**: Extension not activated

**Solutions**:
1. Check extension is installed:
   ```bash
   code --list-extensions | grep platformcontext.platform-context-graph
   ```
2. Reload window: `Cmd+Shift+P` → "Developer: Reload Window"
3. Check for errors: `Help → Toggle Developer Tools → Console`

### Issue 4: Wrong Workspace

**Cause**: VS Code opened wrong directory

**Solution**:
Make sure you opened the correct workspace:
```bash
# Should be the project root with .venv/
code /path/to/PlatformContextGraph
```

## Detailed Error Checking

### Get Full Error Details

1. Open **Developer Tools**: `Help → Toggle Developer Tools`
2. Go to **Console** tab
3. Try indexing again
4. Look for red error messages
5. Copy the full error stack trace

### Check Extension Logs

1. Open **Output** panel: `View → Output`
2. Select **"PlatformContextGraph"** from dropdown
3. Look for error messages or warnings

### Check VS Code Logs

1. Open **Output** panel: `View → Output`
2. Select **"Log (Extension Host)"** from dropdown
3. Look for errors related to PlatformContextGraph

## Manual Testing

### Test 1: Check pcg Path Detection

Create a test file to see what path the extension is using:

1. Open Developer Tools: `Help → Toggle Developer Tools`
2. In Console, type:
   ```javascript
   vscode.workspace.getConfiguration('pcg').get('cliPath')
   ```
3. Should show the detected path

### Test 2: Test pcg Execution

Try running a simple pcg command:

```bash
cd /path/to/PlatformContextGraph
.venv/bin/pcg --help
```

Should show pcg help without errors.

### Test 3: Check Database Connection

```bash
.venv/bin/pcg list
```

Should show indexed projects (or empty if none indexed yet).

## Still Not Working?

### Collect Debug Information

1. **pcg version**:
   ```bash
   .venv/bin/pcg --version
   ```

2. **VS Code version**:
   ```bash
   code --version
   ```

3. **Extension version**:
   ```bash
   code --list-extensions --show-versions | grep platformcontext.platform-context-graph
   ```

4. **Full error from Output panel**:
   - Copy the entire error message from the Output panel

5. **Full error from Developer Tools Console**:
   - Copy any red error messages

### Create an Issue

If still not working, create an issue with:
- All the debug information above
- Steps you tried
- Full error messages
- Screenshots if helpful

## Quick Reference

### Reinstall Extension
```bash
cd /path/to/PlatformContextGraph/vscode-extension
code --uninstall-extension platformcontext.platform-context-graph
code --install-extension platform-context-graph-0.1.0.vsix
# Then: Cmd+Shift+P → "Developer: Reload Window"
```

### Set Manual Path
```
Settings → Search "pcg.cliPath" → Set to:
/path/to/PlatformContextGraph/.venv/bin/pcg
```

### Check Logs
```
View → Output → Select "PlatformContextGraph"
```

### Test pcg
```bash
cd /path/to/PlatformContextGraph
.venv/bin/pcg --version
.venv/bin/pcg list
```

---

**Most likely solution**: Reinstall the extension and reload VS Code window!
