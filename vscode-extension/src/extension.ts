// src/extension.ts
import * as vscode from 'vscode';
import { PcgManager } from './pcgManager';
import { ProjectsTreeProvider } from './providers/projectsTreeProvider';
import { FunctionsTreeProvider } from './providers/functionsTreeProvider';
import { ClassesTreeProvider } from './providers/classesTreeProvider';
import { CallGraphTreeProvider } from './providers/callGraphTreeProvider';
import { DependenciesTreeProvider } from './providers/dependenciesTreeProvider';
import { PcgCodeLensProvider } from './providers/codeLensProvider';
import { PcgDiagnosticsProvider } from './providers/diagnosticsProvider';
import { GraphVisualizationPanel } from './panels/graphVisualizationPanel';
import { ConfigPanel } from './panels/configPanel';
import { StatusBarManager } from './statusBarManager';

let pcgManager: PcgManager;
let statusBarManager: StatusBarManager;
let diagnosticsProvider: PcgDiagnosticsProvider;

export async function activate(context: vscode.ExtensionContext) {
    const debugChannel = vscode.window.createOutputChannel("PlatformContextGraph (Debug)");
    debugChannel.appendLine(`[Activation] Extension activation started at ${new Date().toISOString()}`);
    console.log('PlatformContextGraph extension is now active!');

    try {
        debugChannel.appendLine('[Activation] Initializing PcgManager...');
        // Initialize PCG Manager
        pcgManager = new PcgManager(context);
        debugChannel.appendLine('[Activation] PcgManager initialized successfully');

        statusBarManager = new StatusBarManager();

        // Initialize tree view providers
        const projectsProvider = new ProjectsTreeProvider(pcgManager);
        const functionsProvider = new FunctionsTreeProvider(pcgManager);
        const classesProvider = new ClassesTreeProvider(pcgManager);
        const callGraphProvider = new CallGraphTreeProvider(pcgManager);
        const dependenciesProvider = new DependenciesTreeProvider(pcgManager);

        // Register tree views
        vscode.window.registerTreeDataProvider('pcg-projects', projectsProvider);
        vscode.window.registerTreeDataProvider('pcg-functions', functionsProvider);
        vscode.window.registerTreeDataProvider('pcg-classes', classesProvider);
        vscode.window.registerTreeDataProvider('pcg-callgraph', callGraphProvider);
        vscode.window.registerTreeDataProvider('pcg-dependencies', dependenciesProvider);

        // Register Code Lens Provider
        const config = vscode.workspace.getConfiguration('pcg');
        if (config.get('enableCodeLens')) {
            const codeLensProvider = new PcgCodeLensProvider(pcgManager);
            context.subscriptions.push(
                vscode.languages.registerCodeLensProvider(
                    { scheme: 'file' },
                    codeLensProvider
                )
            );
        }

        // Register Diagnostics Provider
        if (config.get('enableDiagnostics')) {
            diagnosticsProvider = new PcgDiagnosticsProvider(pcgManager);
            context.subscriptions.push(diagnosticsProvider);
        }

        // Register commands
        registerCommands(context, projectsProvider, functionsProvider, classesProvider, callGraphProvider, dependenciesProvider);

        // Auto-index on startup if enabled
        if (config.get('autoIndex')) {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && workspaceFolders.length > 0) {
                statusBarManager.setIndexing(true);
                try {
                    await pcgManager.indexWorkspace(workspaceFolders[0].uri.fsPath);
                    vscode.window.showInformationMessage('Workspace indexed successfully!');
                    refreshAllViews(projectsProvider, functionsProvider, classesProvider, callGraphProvider, dependenciesProvider);
                } catch (error) {
                    vscode.window.showErrorMessage(`Failed to index workspace: ${error}`);
                } finally {
                    statusBarManager.setIndexing(false);
                }
            }
        }

        // Watch for file changes
        const fileWatcher = vscode.workspace.createFileSystemWatcher('**/*');
        fileWatcher.onDidChange(async (uri) => {
            if (config.get('autoIndex')) {
                await pcgManager.updateFile(uri.fsPath);
                refreshAllViews(projectsProvider, functionsProvider, classesProvider, callGraphProvider, dependenciesProvider);
            }
        });
        context.subscriptions.push(fileWatcher);

        vscode.window.showInformationMessage('PlatformContextGraph is ready!');
        debugChannel.appendLine('[Activation] Activation completed successfully.');
    } catch (error) {
        debugChannel.appendLine(`[Activation Error] Failed to activate extension: ${error}`);
        // Log stack trace if available
        if (error instanceof Error && error.stack) {
            debugChannel.appendLine(`[Stack Trace]: ${error.stack}`);
        }
        vscode.window.showErrorMessage(`PlatformContextGraph Activation Failed: ${error}`);
    }
}

function registerCommands(
    context: vscode.ExtensionContext,
    projectsProvider: ProjectsTreeProvider,
    functionsProvider: FunctionsTreeProvider,
    classesProvider: ClassesTreeProvider,
    callGraphProvider: CallGraphTreeProvider,
    dependenciesProvider: DependenciesTreeProvider
) {
    // Index command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.index', async () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders || workspaceFolders.length === 0) {
                vscode.window.showErrorMessage('No workspace folder open');
                return;
            }

            statusBarManager.setIndexing(true);
            try {
                await vscode.window.withProgress({
                    location: vscode.ProgressLocation.Notification,
                    title: 'Indexing workspace...',
                    cancellable: false
                }, async (progress) => {
                    await pcgManager.indexWorkspace(workspaceFolders[0].uri.fsPath);
                });
                vscode.window.showInformationMessage('Workspace indexed successfully!');
                refreshAllViews(projectsProvider, functionsProvider, classesProvider, callGraphProvider, dependenciesProvider);
            } catch (error) {
                vscode.window.showErrorMessage(`Indexing failed: ${error}`);
            } finally {
                statusBarManager.setIndexing(false);
            }
        })
    );

    // Re-index command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.reindex', async () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders || workspaceFolders.length === 0) {
                vscode.window.showErrorMessage('No workspace folder open');
                return;
            }

            statusBarManager.setIndexing(true);
            try {
                await vscode.window.withProgress({
                    location: vscode.ProgressLocation.Notification,
                    title: 'Re-indexing workspace...',
                    cancellable: false
                }, async (progress) => {
                    await pcgManager.reindexWorkspace(workspaceFolders[0].uri.fsPath);
                });
                vscode.window.showInformationMessage('Workspace re-indexed successfully!');
                refreshAllViews(projectsProvider, functionsProvider, classesProvider, callGraphProvider, dependenciesProvider);
            } catch (error) {
                vscode.window.showErrorMessage(`Re-indexing failed: ${error}`);
            } finally {
                statusBarManager.setIndexing(false);
            }
        })
    );

    // Search command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.search', async () => {
            const query = await vscode.window.showInputBox({
                prompt: 'Enter search query (function, class, or file name)',
                placeHolder: 'e.g., processData'
            });

            if (!query) {
                return;
            }

            try {
                const results = await pcgManager.search(query);
                if (results.length === 0) {
                    vscode.window.showInformationMessage('No results found');
                    return;
                }

                // Show results in quick pick
                const items = results.map(r => ({
                    label: r.name,
                    description: r.type,
                    detail: r.file,
                    result: r
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: 'Select an item to navigate to'
                });

                if (selected) {
                    await navigateToLocation(selected.result.file, selected.result.line);
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Search failed: ${error}`);
            }
        })
    );

    // Show call graph command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.showCallGraph', async (item?: any) => {
            let functionName: string | undefined;

            if (item && item.label) {
                functionName = item.label;
            } else {
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    const position = editor.selection.active;
                    const wordRange = editor.document.getWordRangeAtPosition(position);
                    if (wordRange) {
                        functionName = editor.document.getText(wordRange);
                    }
                }
            }

            if (!functionName) {
                functionName = await vscode.window.showInputBox({
                    prompt: 'Enter function name',
                    placeHolder: 'e.g., processData'
                });
            }

            if (!functionName) {
                return;
            }

            try {
                const graphData = await pcgManager.getCallGraph(functionName);
                GraphVisualizationPanel.render(context.extensionUri, graphData, 'Call Graph: ' + functionName);
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to get call graph: ${error}`);
            }
        })
    );

    // Visualize full repository graph command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.visualizeRepo', async (item?: any) => {
            // item may be a ProjectTreeItem clicked from the sidebar, or undefined for the workspace
            const projectPath: string | undefined = item?.projectPath || undefined;
            const label = projectPath
                ? projectPath.split('/').pop() || projectPath
                : (vscode.workspace.workspaceFolders?.[0]?.name || 'Workspace');

            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: `Building full graph for "${label}"…`,
                cancellable: false
            }, async () => {
                try {
                    const graphData = await pcgManager.getRepoGraph(projectPath);
                    if (graphData.nodes.length === 0) {
                        vscode.window.showWarningMessage(
                            `No data found for "${label}". Make sure the workspace is indexed first (PCG: Index Current Workspace).`
                        );
                        return;
                    }
                    GraphVisualizationPanel.render(
                        context.extensionUri,
                        graphData,
                        `Repository Graph: ${label} (${graphData.nodes.length} nodes)`
                    );
                } catch (error) {
                    vscode.window.showErrorMessage(`Failed to build repo graph: ${error}`);
                }
            });
        })
    );


    // Deep / indirect call chain command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.showDeepCallGraph', async (item?: any) => {
            let functionName: string | undefined;

            if (item && item.label) {
                functionName = item.label;
            } else {
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    const wordRange = editor.document.getWordRangeAtPosition(editor.selection.active);
                    if (wordRange) { functionName = editor.document.getText(wordRange); }
                }
            }

            if (!functionName) {
                functionName = await vscode.window.showInputBox({
                    prompt: 'Enter function name to trace call chains for',
                    placeHolder: 'e.g., debug_log'
                });
            }

            if (!functionName) { return; }

            const depthChoice = await vscode.window.showQuickPick(
                [
                    { label: '2 hops', description: 'Callers/callees of callers/callees', depth: 2 },
                    { label: '3 hops', description: 'Three levels deep in both directions', depth: 3 },
                    { label: '5 hops', description: 'Five levels deep — medium chains', depth: 5 },
                    { label: '8 hops', description: 'Eight levels — large chains', depth: 8 },
                    { label: '15 hops', description: 'Full chain traversal (may be large)', depth: 15 },
                ],
                { placeHolder: `How many hops to trace from "${functionName}"?` }
            );

            if (!depthChoice) { return; }
            const depth = depthChoice.depth;

            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: `Tracing ${depth}-hop call chains for "${functionName}"…`,
                cancellable: false
            }, async () => {
                try {
                    const graphData = await pcgManager.getDeepCallGraph(functionName!, depth);
                    if (graphData.nodes.length <= 1) {
                        vscode.window.showWarningMessage(
                            `No indirect call chains found for "${functionName}". ` +
                            `Try indexing the workspace first, or the function may have no connected callers/callees.`
                        );
                        return;
                    }
                    GraphVisualizationPanel.render(
                        context.extensionUri,
                        graphData,
                        `Deep Call Chain: ${functionName} (${depth} hops, ${graphData.nodes.length} nodes)`
                    );
                } catch (error) {
                    vscode.window.showErrorMessage(`Failed to trace call chain: ${error}`);
                }
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.showCallers', async (item?: any) => {

            let functionName: string | undefined;

            if (item && item.label) {
                functionName = item.label;
            } else {
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    const position = editor.selection.active;
                    const wordRange = editor.document.getWordRangeAtPosition(position);
                    if (wordRange) {
                        functionName = editor.document.getText(wordRange);
                    }
                }
            }

            if (!functionName) {
                functionName = await vscode.window.showInputBox({
                    prompt: 'Enter function name',
                    placeHolder: 'e.g., processData'
                });
            }

            if (!functionName) {
                return;
            }

            try {
                const callers = await pcgManager.getCallers(functionName);
                if (callers.length === 0) {
                    vscode.window.showInformationMessage(`No callers found for ${functionName}`);
                    return;
                }

                const items = callers.map(c => ({
                    label: c.name,
                    description: c.file,
                    detail: `Line ${c.line}`,
                    caller: c
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: `Callers of ${functionName}`
                });

                if (selected) {
                    await navigateToLocation(selected.caller.file, selected.caller.line);
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to get callers: ${error}`);
            }
        })
    );

    // Show callees command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.showCallees', async (item?: any) => {
            let functionName: string | undefined;

            if (item && item.label) {
                functionName = item.label;
            } else {
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    const position = editor.selection.active;
                    const wordRange = editor.document.getWordRangeAtPosition(position);
                    if (wordRange) {
                        functionName = editor.document.getText(wordRange);
                    }
                }
            }

            if (!functionName) {
                functionName = await vscode.window.showInputBox({
                    prompt: 'Enter function name',
                    placeHolder: 'e.g., processData'
                });
            }

            if (!functionName) {
                return;
            }

            try {
                const callees = await pcgManager.getCallees(functionName);
                if (callees.length === 0) {
                    vscode.window.showInformationMessage(`No callees found for ${functionName}`);
                    return;
                }

                const items = callees.map(c => ({
                    label: c.name,
                    description: c.file,
                    detail: `Line ${c.line}`,
                    callee: c
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: `Callees of ${functionName}`
                });

                if (selected) {
                    await navigateToLocation(selected.callee.file, selected.callee.line);
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to get callees: ${error}`);
            }
        })
    );

    // Find dependencies command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.findDependencies', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showErrorMessage('No active editor');
                return;
            }

            try {
                const filePath = editor.document.uri.fsPath;
                const dependencies = await pcgManager.getDependencies(filePath);

                if (dependencies.length === 0) {
                    vscode.window.showInformationMessage('No dependencies found');
                    return;
                }

                const items = dependencies.map(d => ({
                    label: d.name,
                    description: d.type,
                    detail: d.file,
                    dependency: d
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: 'Dependencies'
                });

                if (selected && selected.dependency.file) {
                    await navigateToLocation(selected.dependency.file, selected.dependency.line || 1);
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to get dependencies: ${error}`);
            }
        })
    );

    // Analyze calls command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.analyzeCalls', async () => {
            try {
                const results = await pcgManager.analyzeCalls();

                const panel = vscode.window.createWebviewPanel(
                    'pcgCallAnalysis',
                    'Call Analysis',
                    vscode.ViewColumn.Two,
                    { enableScripts: true }
                );

                panel.webview.html = generateCallAnalysisHtml(results);
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to analyze calls: ${error}`);
            }
        })
    );

    // Analyze complexity command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.analyzeComplexity', async () => {
            const config = vscode.workspace.getConfiguration('pcg');
            const threshold = config.get<number>('complexityThreshold') || 10;

            try {
                const results = await pcgManager.analyzeComplexity(threshold);

                if (results.length === 0) {
                    vscode.window.showInformationMessage('No complex functions found');
                    return;
                }

                const items = results.map(r => ({
                    label: r.name,
                    description: `Complexity: ${r.complexity}`,
                    detail: r.file,
                    result: r
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: `Functions with complexity > ${threshold}`
                });

                if (selected) {
                    await navigateToLocation(selected.result.file, selected.result.line);
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to analyze complexity: ${error}`);
            }
        })
    );

    // Find dead code command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.findDeadCode', async () => {
            try {
                const results = await pcgManager.findDeadCode();

                if (results.length === 0) {
                    vscode.window.showInformationMessage('No dead code found');
                    return;
                }

                const items = results.map(r => ({
                    label: r.name,
                    description: r.type,
                    detail: r.file,
                    result: r
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: 'Dead code (unused functions/classes)'
                });

                if (selected) {
                    await navigateToLocation(selected.result.file, selected.result.line);
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to find dead code: ${error}`);
            }
        })
    );

    // Show stats command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.showStats', async () => {
            try {
                const stats = await pcgManager.getStats();

                const panel = vscode.window.createWebviewPanel(
                    'pcgStats',
                    'PCG Statistics',
                    vscode.ViewColumn.Two,
                    { enableScripts: true }
                );

                panel.webview.html = generateStatsHtml(stats);
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to get statistics: ${error}`);
            }
        })
    );

    // Show inheritance tree command — accepts a tree item OR falls back to input box
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.showInheritance', async (item?: any) => {
            let className: string | undefined;

            if (item && item.label) {
                className = item.label;
            } else {
                className = await vscode.window.showInputBox({
                    prompt: 'Enter class name',
                    placeHolder: 'e.g., BaseController'
                });
            }

            if (!className) { return; }

            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: `Building inheritance tree for "${className}"…`,
                cancellable: false
            }, async () => {
                try {
                    const graphData = await pcgManager.getInheritanceTree(className!);
                    if (graphData.nodes.length <= 1) {
                        vscode.window.showInformationMessage(
                            `No inheritance relationships found for "${className}". ` +
                            `The class may not inherit from or be inherited by anything in the index.`
                        );
                        return;
                    }
                    GraphVisualizationPanel.render(
                        context.extensionUri, graphData,
                        `Inheritance: ${className} (${graphData.nodes.length} classes)`
                    );
                } catch (error) {
                    vscode.window.showErrorMessage(`Failed to get inheritance tree: ${error}`);
                }
            });
        })
    );

    // Load bundle command
    // Open PCG configuration (.env editor)
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.openConfig', () => {
            ConfigPanel.render(context.extensionUri);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.loadBundle', async () => {
            const bundleName = await vscode.window.showInputBox({
                prompt: 'Enter bundle name (e.g., numpy, pandas)',
                placeHolder: 'numpy'
            });

            if (!bundleName) {
                return;
            }

            try {
                await vscode.window.withProgress({
                    location: vscode.ProgressLocation.Notification,
                    title: `Loading bundle: ${bundleName}...`,
                    cancellable: false
                }, async (progress) => {
                    await pcgManager.loadBundle(bundleName);
                });
                vscode.window.showInformationMessage(`Bundle ${bundleName} loaded successfully!`);
                refreshAllViews(projectsProvider, functionsProvider, classesProvider, callGraphProvider, dependenciesProvider);
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to load bundle: ${error}`);
            }
        })
    );

    // Open settings command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.openSettings', () => {
            vscode.commands.executeCommand('workbench.action.openSettings', 'pcg');
        })
    );

    // Refresh explorer command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.refreshExplorer', () => {
            refreshAllViews(projectsProvider, functionsProvider, classesProvider, callGraphProvider, dependenciesProvider);
        })
    );

    // Go to definition command
    context.subscriptions.push(
        vscode.commands.registerCommand('pcg.goToDefinition', async (item: any) => {
            if (item && item.file && item.line) {
                await navigateToLocation(item.file, item.line);
            }
        })
    );
}

function refreshAllViews(
    projectsProvider: ProjectsTreeProvider,
    functionsProvider: FunctionsTreeProvider,
    classesProvider: ClassesTreeProvider,
    callGraphProvider: CallGraphTreeProvider,
    dependenciesProvider: DependenciesTreeProvider
) {
    projectsProvider.refresh();
    functionsProvider.refresh();
    classesProvider.refresh();
    callGraphProvider.refresh();
    dependenciesProvider.refresh();

    // Refresh diagnostics if enabled
    if (diagnosticsProvider) {
        diagnosticsProvider.refresh();
    }
}

async function navigateToLocation(file: string, line: number) {
    const uri = vscode.Uri.file(file);
    const document = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(document);
    const position = new vscode.Position(Math.max(0, line - 1), 0);
    editor.selection = new vscode.Selection(position, position);
    editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenter);
}

function generateCallAnalysisHtml(results: any[]): string {
    const rows = results.map(r => `
        <tr>
            <td>${r.caller}</td>
            <td>${r.callee}</td>
            <td>${r.file}</td>
            <td>${r.line}</td>
        </tr>
    `).join('');

    return `
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: var(--vscode-font-family); padding: 20px; }
                table { width: 100%; border-collapse: collapse; }
                th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--vscode-panel-border); }
                th { background-color: var(--vscode-editor-background); }
            </style>
        </head>
        <body>
            <h1>Call Analysis</h1>
            <table>
                <thead>
                    <tr>
                        <th>Caller</th>
                        <th>Callee</th>
                        <th>File</th>
                        <th>Line</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </body>
        </html>
    `;
}

function generateStatsHtml(stats: any): string {
    return `
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { 
                    font-family: var(--vscode-font-family); 
                    padding: 20px;
                    color: var(--vscode-foreground);
                }
                .stat-card {
                    background: var(--vscode-editor-background);
                    border: 1px solid var(--vscode-panel-border);
                    border-radius: 8px;
                    padding: 20px;
                    margin: 10px 0;
                }
                .stat-title {
                    font-size: 14px;
                    color: var(--vscode-descriptionForeground);
                    margin-bottom: 5px;
                }
                .stat-value {
                    font-size: 32px;
                    font-weight: bold;
                    color: var(--vscode-textLink-foreground);
                }
                .grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                }
            </style>
        </head>
        <body>
            <h1>Project Statistics</h1>
            <div class="grid">
                <div class="stat-card">
                    <div class="stat-title">Total Files</div>
                    <div class="stat-value">${stats.files || 0}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Total Functions</div>
                    <div class="stat-value">${stats.functions || 0}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Total Classes</div>
                    <div class="stat-value">${stats.classes || 0}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Total Calls</div>
                    <div class="stat-value">${stats.calls || 0}</div>
                </div>
            </div>
        </body>
        </html>
    `;
}

export function deactivate() {
    if (pcgManager) {
        pcgManager.dispose();
    }
    if (statusBarManager) {
        statusBarManager.dispose();
    }
}
