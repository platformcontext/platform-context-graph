// src/statusBarManager.ts
import * as vscode from 'vscode';

export class StatusBarManager {
    private statusBarItem: vscode.StatusBarItem;

    constructor() {
        this.statusBarItem = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Left,
            100
        );
        this.statusBarItem.command = 'pcg.showStats';
        this.setReady();
        this.statusBarItem.show();
    }

    public setIndexing(isIndexing: boolean): void {
        if (isIndexing) {
            this.statusBarItem.text = '$(sync~spin) PCG: Indexing...';
            this.statusBarItem.tooltip = 'PlatformContextGraph is indexing the workspace';
        } else {
            this.setReady();
        }
    }

    public setReady(): void {
        this.statusBarItem.text = '$(database) PCG: Ready';
        this.statusBarItem.tooltip = 'PlatformContextGraph is ready. Click for statistics.';
    }

    public setError(message: string): void {
        this.statusBarItem.text = '$(error) PCG: Error';
        this.statusBarItem.tooltip = `PlatformContextGraph error: ${message}`;
    }

    public dispose(): void {
        this.statusBarItem.dispose();
    }
}
