import React from "react";
import { FolderOpen, FileText, RefreshCw, File } from "lucide-react";

interface WorkspaceFile {
  name: string;
  path: string;
  size: number;
}

interface FileBrowserProps {
  files: WorkspaceFile[];
  onRefresh: () => void;
}

export const FileBrowser: React.FC<FileBrowserProps> = ({ files, onRefresh }) => {
  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  };

  const getFileIcon = (name: string) => {
    if (name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".json")) {
      return <FileText size={16} className="text-secondary" />;
    }
    return <File size={16} className="text-muted" />;
  };

  return (
    <div className="file-browser flex flex-column h-full">
      <div className="panel-header flex align-items-center justify-content-between">
        <h3 className="panel-title flex align-items-center gap-2">
          <FolderOpen size={18} className="panel-icon" />
          <span>Workspace Files</span>
        </h3>
        <button
          className="refresh-btn p-1 flex align-items-center justify-content-center border-radius-sm pointer"
          onClick={onRefresh}
          title="Refresh file list"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      <div className="file-content flex-grow overflow-y-auto p-3">
        <ul className="file-list list-none p-0 m-0">
          {files.map((file) => (
            <li
              key={file.path}
              className="file-item flex align-items-center justify-content-between p-2 border-radius-sm mb-1"
            >
              <div className="flex align-items-center gap-2 text-ellipsis flex-grow">
                {getFileIcon(file.name)}
                <span className="file-name font-mono text-sm text-ellipsis" title={file.path}>
                  {file.name}
                </span>
              </div>
              <span className="file-size text-xs text-muted font-mono whitespace-nowrap ml-2">
                {formatBytes(file.size)}
              </span>
            </li>
          ))}
          {files.length === 0 && (
            <div className="text-muted text-center p-4 text-sm font-mono">
              No files in workspace data/ folder yet.
            </div>
          )}
        </ul>
      </div>
    </div>
  );
};
