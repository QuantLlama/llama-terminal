const { useState, useEffect, useRef, useCallback, useMemo, useLayoutEffect } = React;

const FloatingModal = ({ isOpen, width = 420, maxHeight = '80vh', zIndex = 10000, initialY = 140, header, onClose, children, storageKey }) => {
  const clampPos = (p) => {
    if (typeof window === 'undefined') return p;
    const maxX = Math.max(0, window.innerWidth - width);
    const maxY = Math.max(0, window.innerHeight - 50);
    return { x: Math.min(Math.max(0, p.x), maxX), y: Math.min(Math.max(0, p.y), maxY) };
  };
  const [pos, setPos] = useState(() => {
    if (typeof window === 'undefined') return { x: 24, y: 24 };
    const defaultPos = {
      x: Math.max(24, (window.innerWidth - width) / 2),
      y: Math.max(24, (window.innerHeight - 300) / 2)
    };
    if (storageKey) {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) return clampPos(JSON.parse(saved));
      } catch (e) { }
    }
    return clampPos(defaultPos);
  });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef(null);
  const offsetRef = useRef({ x: 0, y: 0 });
  const initializedRef = useRef(false);
  useLayoutEffect(() => {
    if (!isOpen) return;
    if (initializedRef.current) return;
    if (storageKey) {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          setPos(clampPos(JSON.parse(saved)));
          initializedRef.current = true;
          return;
        }
      } catch (e) { }
    }
    setPos(clampPos({
      x: Math.max(24, (window.innerWidth - width) / 2),
      y: Math.max(24, (window.innerHeight - 300) / 2)
    }));
    initializedRef.current = true;
  }, [isOpen, width, initialY, storageKey]);
  const handleMouseDown = (e) => {
    if (!e.target.closest('.drag-handle')) return;
    const targetTag = e.target.tagName.toLowerCase();
    if (targetTag !== 'button' && targetTag !== 'input' && targetTag !== 'textarea') {
      e.preventDefault();
    }
    setDragging(true);
    const rect = dragRef.current.getBoundingClientRect();
    offsetRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };
  useEffect(() => {
    if (!dragging) return;
    const move = (e) => {
      setPos(clampPos({
        x: e.clientX - offsetRef.current.x,
        y: e.clientY - offsetRef.current.y
      }));
    };
    const stop = () => {
      setDragging(false);
    };
    window.addEventListener('mousemove', move, true);
    window.addEventListener('mouseup', stop, true);
    return () => {
      window.removeEventListener('mousemove', move, true);
      window.removeEventListener('mouseup', stop, true);
    };
  }, [dragging]);
  useEffect(() => {
    if (!dragging && initializedRef.current && storageKey) {
      try { localStorage.setItem(storageKey, JSON.stringify(pos)); } catch (e) { }
    }
  }, [dragging, pos, storageKey]);
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 pointer-events-none overflow-hidden", style: { zIndex } },
      React.createElement("div", {
        ref: dragRef,
        onMouseDown: handleMouseDown,
        style: { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px`, width, maxHeight },
        className: "pointer-events-auto bg-panel border border-border rounded-xl shadow-2xl backdrop-blur-3xl flex flex-col overflow-hidden"
      },
        React.createElement("div", { className: "drag-handle flex items-center justify-between px-4 py-3 bg-white/5 border-b border-white/5 cursor-move" },
          React.createElement("div", { className: "flex items-center gap-3" }, header),
          React.createElement("button", { onClick: onClose, className: "text-muted hover:text-white transition-colors" },
            React.createElement("i", { className: "fas fa-times text-xs" })
          )
        ),
        React.createElement("div", { className: "flex-1 overflow-y-auto p-5 no-scrollbar" },
          children
        )
      )
    )
  );
};

const AlgoLab = ({ isOpen }) => {
  const [files, setFiles] = useState({ indicators: [], strategies: [] });
  const [openFiles, setOpenFiles] = useState([]);
  const [activeFile, setActiveFile] = useState(null);
  const [fileContents, setFileContents] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [showNewFileModal, setShowNewFileModal] = useState(false);
  const [newFileType, setNewFileType] = useState('indicator');
  const [newFileName, setNewFileName] = useState('');
  const [terminalHeight, setTerminalHeight] = useState(250);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [aiSettings, setAiSettings] = useState({ apiKey: '', provider: 'openrouter', model: 'openai/gpt-3.5-turbo' });
  const [showAiSettings, setShowAiSettings] = useState(false);
  const [sidebarMode, setSidebarMode] = useState('explorer');
  const [chatWidth, setChatWidth] = useState(350);
  const [agenticMode, setAgenticMode] = useState(() => {
    const saved = localStorage.getItem('algolab_agentic_mode');
    return saved ? JSON.parse(saved) : true;
  });
  const [previousContent, setPreviousContent] = useState(null);
  const [isAiWriting, setIsAiWriting] = useState(false);
  const [isReviewingDiff, setIsReviewingDiff] = useState(false);
  const [availableModels, setAvailableModels] = useState([]);
  const [isFetchingModels, setIsFetchingModels] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [contextMenu, setContextMenu] = useState({ visible: false, x: 0, y: 0, file: null });
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [fileToDelete, setFileToDelete] = useState(null);
  const [renameName, setRenameName] = useState('');
  const [missingDependencies, setMissingDependencies] = useState([]);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  const [isInstallingDeps, setIsInstallingDeps] = useState(false);
  const [isEditorReady, setIsEditorReady] = useState(false);
  const [terminalLoaded, setTerminalLoaded] = useState(false);
  const [showFallback, setShowFallback] = useState(false);
  const [fallbackContent, setFallbackContent] = useState('');
  const [fallbackScroll, setFallbackScroll] = useState({ top: 0, height: 20, visible: false });
  const isElectronEnv = typeof window !== 'undefined' && (
    window.electronAPI && window.electronAPI.isElectron ||
    window.process && window.process.type === 'renderer' ||
    typeof navigator !== 'undefined' && navigator.userAgent.toLowerCase().includes(' electron/'));
  const isResizingChat = useRef(false);
  const chatEndRef = useRef(null);
  const editorRef = useRef(null);
  const diffEditorRef = useRef(null);
  const terminalContainerRef = useRef(null);
  const xtermRef = useRef(null);
  const socketRef = useRef(null);
  const isResizingTerminal = useRef(false);
  const isResizingSidebar = useRef(false);
  const abortControllerRef = useRef(null);
  const editorContainerRef = useRef(null);
  const diffEditorContainerRef = useRef(null);
  const pendingContentRef = useRef(null);
  const fallbackContentRef = useRef('');
  const fallbackPreRef = useRef(null);
  const fallbackTextareaRef = useRef(null);
  const fallbackEditorRef = useRef(null);
  const caretOffsetRef = useRef(0);
  const fallbackAttemptRef = useRef(0);
  const pythonCompletionRegisteredRef = useRef(false);
  // FloatingModal has been moved outside AlgoLab to prevent re-renders on every keystroke
  const openFilesRef = useRef(openFiles);
  const activeFileRef = useRef(activeFile);
  const fileContentsRef = useRef(fileContents);
  const isChatOpenRef = useRef(isChatOpen);
  const chatWidthRef = useRef(chatWidth);
  const modelsRef = useRef(new Map());
  const getLanguageFromFile = (file) => {
    const filename = (file?.name || '').toLowerCase();
    if (filename.endsWith('.js') || filename.endsWith('.jsx')) return 'javascript';
    if (filename.endsWith('.ts') || filename.endsWith('.tsx')) return 'typescript';
    if (filename.endsWith('.html')) return 'html';
    if (filename.endsWith('.css') || filename.endsWith('.scss')) return 'css';
    if (filename.endsWith('.json')) return 'json';
    if (filename.endsWith('.yml') || filename.endsWith('.yaml')) return 'yaml';
    if (filename.endsWith('.md')) return 'markdown';
    if (filename.endsWith('.py')) return 'python';
    return 'plaintext';
  };
  const escapeHtml = (text) => {
    if (text === undefined || text === null) return '';
    return text.
      replace(/&/g, '&amp;').
      replace(/</g, '&lt;').
      replace(/>/g, '&gt;');
  };
  const buildHighlightPattern = (lang) => {
    const keywordsByLang = {
      python: ['def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'finally', 'with', 'as', 'import', 'from', 'pass', 'break', 'continue', 'lambda', 'yield', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is', 'global', 'nonlocal', 'assert', 'raise'],
      javascript: ['function', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'finally', 'switch', 'case', 'break', 'continue', 'const', 'let', 'var', 'new', 'class', 'extends', 'super', 'this', 'import', 'from', 'export', 'default', 'true', 'false', 'null', 'undefined', 'async', 'await', 'yield', 'throw', 'typeof', 'instanceof'],
      typescript: ['function', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'finally', 'switch', 'case', 'break', 'continue', 'const', 'let', 'var', 'new', 'class', 'extends', 'super', 'this', 'import', 'from', 'export', 'default', 'true', 'false', 'null', 'undefined', 'async', 'await', 'yield', 'throw', 'typeof', 'instanceof', 'interface', 'type', 'implements', 'public', 'private', 'protected', 'readonly', 'enum'],
      json: ['true', 'false', 'null'],
      yaml: ['true', 'false', 'null', 'yes', 'no']
    };
    const commentPattern = (() => {
      if (lang === 'python') return /#.*$/gm;
      if (lang === 'javascript' || lang === 'typescript') return /\/\/.*$|\/\*[\s\S]*?\*\//gm;
      if (lang === 'css') return /\/\*[\s\S]*?\*\//gm;
      if (lang === 'html') return /&lt;!--[\s\S]*?--&gt;/gm;
      return null;
    })();
    const stringPattern = (() => {
      if (lang === 'python') return /"(?:\\.|[^"])*"|'(?:\\.|[^'])*'/gm;
      if (lang === 'javascript' || lang === 'typescript') return /"(?:\\.|[^"])*"|'(?:\\.|[^'])*'|`(?:\\.|[^`])*`/gm;
      if (lang === 'json' || lang === 'yaml') return /"(?:\\.|[^"])*"/gm;
      if (lang === 'html' || lang === 'css') return /"(?:\\.|[^"])*"|'(?:\\.|[^'])*'/gm;
      return /"(?:\\.|[^"])*"|'(?:\\.|[^'])*'/gm;
    })();
    const tagPattern = lang === 'html' ? /&lt;\/?[^&gt;]+&gt;/gm : null;
    const numberPattern = /\b\d+(?:\.\d+)?\b/gm;
    const keywords = keywordsByLang[lang] || [];
    const keywordPattern = keywords.length ? new RegExp(`\\b(?:${keywords.join('|')})\\b`, 'gm') : null;
    const parts = [];
    const classes = [];
    if (tagPattern) { parts.push(tagPattern.source); classes.push('tag'); }
    if (commentPattern) { parts.push(commentPattern.source); classes.push('comment'); }
    if (stringPattern) { parts.push(stringPattern.source); classes.push('string'); }
    if (numberPattern) { parts.push(numberPattern.source); classes.push('number'); }
    if (keywordPattern) { parts.push(keywordPattern.source); classes.push('keyword'); }
    if (parts.length === 0) return null;
    const grouped = parts.map((p) => `(${p})`).join('|');
    return { regex: new RegExp(grouped, 'gm'), classes };
  };
  const highlightCode = (code, lang) => {
    const escaped = escapeHtml(code);
    const pattern = buildHighlightPattern(lang);
    if (!pattern) return escaped;
    const colorMap = {
      comment: '#6b7280',
      string: '#ce9178',
      number: '#b5cea8',
      keyword: '#569cd6',
      tag: '#569cd6'
    };
    return escaped.replace(pattern.regex, (...args) => {
      for (let i = 1; i <= pattern.classes.length; i += 1) {
        if (args[i]) {
          const cls = pattern.classes[i - 1];
          const color = colorMap[cls] || '#e5e7eb';
          return `<span style="color:${color}">${args[i]}</span>`;
        }
      }
      return args[0];
    });
  };
  const pythonKeywords = ['def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'finally', 'with', 'as', 'import', 'from', 'pass', 'break', 'continue', 'lambda', 'yield', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is', 'global', 'nonlocal', 'assert', 'raise'];
  const registerPythonCompletions = () => {
    if (pythonCompletionRegisteredRef.current || !window.monaco) return;
    pythonCompletionRegisteredRef.current = true;
    window.monaco.languages.registerCompletionItemProvider('python', {
      provideCompletionItems: (model, position) => {
        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn
        };
        const suggestions = pythonKeywords.map((kw) => ({
          label: kw,
          kind: window.monaco.languages.CompletionItemKind.Keyword,
          insertText: kw,
          range
        }));
        return { suggestions };
      }
    });
  };
  const getCaretOffset = (el) => {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return 0;
    const range = selection.getRangeAt(0);
    const preRange = range.cloneRange();
    preRange.selectNodeContents(el);
    preRange.setEnd(range.endContainer, range.endOffset);
    return preRange.toString().length;
  };
  const setCaretOffset = (el, offset) => {
    let current = 0;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    let node = walker.nextNode();
    while (node) {
      const length = node.nodeValue.length;
      if (current + length >= offset) {
        const range = document.createRange();
        range.setStart(node, offset - current);
        range.collapse(true);
        const selection = window.getSelection();
        if (selection) {
          selection.removeAllRanges();
          selection.addRange(range);
        }
        return;
      }
      current += length;
      node = walker.nextNode();
    }
  };
  const fallbackLanguage = useMemo(() => getLanguageFromFile(activeFile), [activeFile]);
  const highlightedFallback = useMemo(
    () => highlightCode(fallbackContent, fallbackLanguage),
    [fallbackContent, fallbackLanguage]
  );
  const updateFallbackScroll = useCallback(() => {
    const el = fallbackEditorRef.current;
    if (!el) return;
    const scrollHeight = el.scrollHeight;
    const clientHeight = el.clientHeight;
    const maxScroll = Math.max(0, scrollHeight - clientHeight);
    const height = scrollHeight > 0 ? Math.max(20, clientHeight * clientHeight / scrollHeight) : 20;
    const top = maxScroll > 0 ? el.scrollTop / maxScroll * (clientHeight - height) : 0;
    setFallbackScroll({ top, height, visible: maxScroll > 0 });
  }, []);
  useEffect(() => {
    const el = fallbackEditorRef.current;
    if (!el) return;
    const offset = caretOffsetRef.current;
    el.innerHTML = highlightedFallback || '';
    setCaretOffset(el, offset);
    requestAnimationFrame(updateFallbackScroll);
  }, [highlightedFallback, updateFallbackScroll]);
  const normalizePath = (path) => {
    if (!path) return '';
    return path.replace(/\\/g, '/');
  };

  const forceElectronRepaint = useCallback((editor) => {
    if (!editor) return;
    try {
      editor.layout();
      const domNode = editor.getDomNode();
      if (domNode) {
        const originalDisplay = domNode.style.display;
        domNode.style.display = 'none';
        void domNode.offsetHeight;
        domNode.style.display = originalDisplay || 'block';
      }
      setTimeout(() => {
        if (editor) {
          editor.layout();
          // Ensure it reveals the first line to trigger rendering
          editor.revealLine(1);
        }
      }, 300);
    } catch (e) {
      console.warn('[AlgoLab] Repaint error:', e);
    }
  }, []);
  const setEditorContent = useCallback((content, file) => {
    const container = editorContainerRef.current;
    if (!window.monaco || !container) return;
    
    const normalizedPath = normalizePath(file?.path || 'untitled');

    if (content !== undefined && content !== null) {
      fallbackContentRef.current = content;
      setFallbackContent(content);
    }
    
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (width === 0 && height === 0) {
      pendingContentRef.current = { content, file };
      return;
    }

    if (!editorRef.current) {
      console.log('[AlgoLab] Creating new Monaco instance');
      container.innerHTML = '';
      editorRef.current = window.monaco.editor.create(container, {
        value: '',
        language: 'python',
        theme: 'safe-dark',
        fontSize: 14,
        fontFamily: 'JetBrains Mono',
        automaticLayout: true,
        minimap: { enabled: true },
        scrollBeyondLastLine: false,
        padding: { top: 10 },
        readOnly: false
      });
    }

    const editor = editorRef.current;
    const lang = getLanguageFromFile(file);
    
    try {
      const modelUri = window.monaco.Uri.file(normalizedPath);
      let targetModel = window.monaco.editor.getModel(modelUri);
      
      if (targetModel) {
        if (targetModel.getValue() !== content) {
          targetModel.setValue(content);
        }
      } else {
        targetModel = window.monaco.editor.createModel(content, lang, modelUri);
      }
      
      editor.setModel(targetModel);
      window.monaco.editor.setModelLanguage(targetModel, lang);
      pendingContentRef.current = null;
      
      // Safety: layout immediately and after delay
      editor.layout();
      forceElectronRepaint(editor);
    } catch (err) {
      console.error('[AlgoLab] Model error:', err);
      // Fallback: simple set value if URI fails
      editor.setValue(content || '');
    }
  }, [forceElectronRepaint]);
  useEffect(() => { openFilesRef.current = openFiles; }, [openFiles]);
  useEffect(() => { activeFileRef.current = activeFile; }, [activeFile]);
  useEffect(() => { fileContentsRef.current = fileContents; }, [fileContents]);
  useEffect(() => { isChatOpenRef.current = isChatOpen; }, [isChatOpen]);
  useEffect(() => { chatWidthRef.current = chatWidth; }, [chatWidth]);
  useEffect(() => {
    if (!activeFile) return;
    const content = fileContents[activeFile.path] ?? fileContentsRef.current[activeFile.path] ?? '';
    fallbackContentRef.current = content;
    setFallbackContent(content);
  }, [activeFile, fileContents]);
  useEffect(() => {
    if (!activeFile) return;
    setShowFallback(false);
  }, [activeFile]);
  const getOrCreateModel = (file, content) => {
    if (!window.monaco) return null;
    let model = modelsRef.current.get(file.path);
    if (model && !model.isDisposed()) {
      if (content !== undefined && content !== null && model.getValue() !== content) {
        model.setValue(content);
      }
      return model;
    }
    const lang = getLanguageFromFile(file);
    const uri = window.monaco.Uri.parse(`file://${file.path}`);
    const existing = window.monaco.editor.getModel(uri);
    if (existing) {
      model = existing;
      if (content !== undefined) model.setValue(content);
    } else {
      model = window.monaco.editor.createModel(content || '', lang, uri);
    }
    modelsRef.current.set(file.path, model);
    return model;
  };
  const createMonacoEditor = useCallback(() => {
    const container = editorContainerRef.current;
    
    if (!container || editorRef.current || !window.monaco || !window.monaco.editor) {
      return;
    }
    
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (width === 0 && height === 0) {
      return;
    }

    container.innerHTML = '';
    window.monaco.editor.defineTheme('safe-dark', {
      base: 'vs-dark', inherit: true, rules: [],
      colors: {
        'editor.background': '#1e1e1e', 'editor.foreground': '#d4d4d4',
        'editor.lineHighlightBackground': '#2d2d30',
        'editorCursor.foreground': '#aeafad', 'editorWhitespace.foreground': '#404040'
      }
    });
    editorRef.current = window.monaco.editor.create(container, {
      value: '', language: 'python', theme: 'safe-dark',
      fontSize: 14, fontFamily: 'JetBrains Mono', automaticLayout: false,
      minimap: { enabled: true }, scrollBeyondLastLine: false, padding: { top: 10 }
    });
    if (window.monaco.languages && !window.monaco.languages.getLanguages().some((l) => l.id === 'python')) {
      console.warn("[AlgoLab] Python language missing. Attempting manual load via AMD...");
      if (window.monacoRequire) {
        window.monacoRequire(['vs/basic-languages/python/python'], () => {
          if (editorRef.current) {
            const model = editorRef.current.getModel();
            if (model) window.monaco.editor.setModelLanguage(model, 'python');
          }
        });
      }
    }
    if (!document.getElementById('monaco-electron-fix')) {
      const style = document.createElement('style');
      style.id = 'monaco-electron-fix';
      style.innerHTML = [
        '.monaco-editor{width:100%!important;height:100%!important;opacity:1!important;visibility:visible!important}',
        '.monaco-editor,.monaco-editor-background,.monaco-editor .inputarea.ime-input{background-color:#1e1e1e!important}',
        '.monaco-editor .margin{background-color:#1e1e1e!important}',
        '.monaco-editor .view-lines{font-family:"JetBrains Mono",monospace!important}',
        '.monaco-editor .view-overlays .current-line { border: 2px solid transparent !important; }',
        '.monaco-editor .view-lines { visibility: visible !important; opacity: 1 !important; }',
        '.monaco-scrollable-element { visibility: visible !important; opacity: 1 !important; }',
        '.monaco-editor .lines-content { visibility: visible !important; }',
        '.fallback-editor{scrollbar-color:#3a3a3a #141414;}',
        '.fallback-editor::-webkit-scrollbar{width:10px;height:10px;}',
        '.fallback-editor::-webkit-scrollbar-track{background:#141414;}',
        '.fallback-editor::-webkit-scrollbar-thumb{background:#3a3a3a;border-radius:6px;}',
        '.fallback-editor::-webkit-scrollbar-thumb:hover{background:#4a4a4a;}',
        '.fallback-code { white-space: pre; background:#111827; color:#e5e7eb; }',
        '.fallback-code .token-comment { color: #6b7280; }',
        '.fallback-code .token-string { color: #ce9178; }',
        '.fallback-code .token-number { color: #b5cea8; }',
        '.fallback-code .token-keyword { color: #569cd6; }',
        '.fallback-code .token-tag { color: #569cd6; }'].
        join('');
      document.head.appendChild(style);
    }
    setIsEditorReady(true);
    window.dispatchEvent(new Event('resize'));
    const loadContent = () => {
      if (!editorRef.current) return;
      editorRef.current.layout();
      if (activeFileRef.current) {
        const content = fileContentsRef.current[activeFileRef.current.path];
        if (content !== undefined) {
          const file = activeFileRef.current;
          const filename = (file?.name || '').toLowerCase();
          let lang = 'python';
          if (filename.endsWith('.js') || filename.endsWith('.jsx')) lang = 'javascript';
          if (filename.endsWith('.ts') || filename.endsWith('.tsx')) lang = 'typescript';
          if (filename.endsWith('.html')) lang = 'html';
          if (filename.endsWith('.css')) lang = 'css';
          if (filename.endsWith('.json')) lang = 'json';
          const uri = window.monaco.Uri.parse(`file:///${file.path}`);
          let model = window.monaco.editor.getModel(uri);
          if (!model) {
            model = window.monaco.editor.createModel(content, lang, uri);
          } else if (model.getValue() !== content) {
            model.setValue(content);
          }
          if (editorRef.current.getModel() !== model) {
            editorRef.current.setModel(model);
          }
          window.monaco.editor.setModelLanguage(model, lang);
        }
      }
      const domNode = editorRef.current.getDomNode();
      if (domNode) {
        domNode.style.display = 'none';
        void domNode.offsetHeight;
        domNode.style.display = 'block';
      }
      requestAnimationFrame(() => requestAnimationFrame(() => {
        editorRef.current?.layout();
      }));
    };
    loadContent();
    setTimeout(loadContent, 300);
    setTimeout(loadContent, 800);
  }, []);
  useEffect(() => {
    const setup = async () => {
      const loadScript = (url) => new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${url}"]`)) { resolve(); return; }
        const s = document.createElement('script');
        s.src = url; s.async = true; s.onload = resolve; s.onerror = reject;
        document.head.appendChild(s);
      });
      const loadCSS = (url) => {
        if (document.querySelector(`link[href="${url}"]`)) return;
        const link = document.createElement('link');
        link.rel = 'stylesheet'; link.href = url;
        document.head.appendChild(link);
      };

      // Monaco Worker Configuration
      const origin = window.location.origin;
      window.MonacoEnvironment = {
        getWorkerUrl: function (workerId, label) {
          const wp = 'lib/monaco/vs/base/worker/workerMain.js';
          const fullWorkerPath = `${origin}/${wp}`;
          const workerCode = `self.MonacoEnvironment={baseUrl:'${origin}/lib/monaco/vs/'};importScripts('${fullWorkerPath}');`;
          if (window.URL && window.URL.createObjectURL) {
            const blob = new Blob([workerCode], { type: 'text/javascript' });
            return window.URL.createObjectURL(blob);
          }
          return `data:text/javascript;charset=utf-8,${encodeURIComponent(workerCode)}`;
        }
      };

      const initMonacoWithObserver = () => {
        const container = editorContainerRef.current;
        if (!container) return;
        registerPythonCompletions();
        const observer = new ResizeObserver(() => {
          if ((container.clientWidth > 0 || container.clientHeight > 0) && window.monaco && window.monaco.editor && !editorRef.current) {
            createMonacoEditor();
          }
          if (editorRef.current) requestAnimationFrame(() => editorRef.current.layout());
          if (pendingContentRef.current && (container.clientWidth > 0 || container.clientHeight > 0)) {
            const pending = pendingContentRef.current;
            setEditorContent(pending.content, pending.file);
            pendingContentRef.current = null;
          }
        });
        observer.observe(container);
        if ((container.clientWidth > 0 || container.clientHeight > 0) && window.monaco && window.monaco.editor && !editorRef.current) {
          createMonacoEditor();
        }
      };
      // ===== STEP 1: Load Xterm FIRST (before Monaco interval) =====
      // CRITICAL: Monaco's loader.js sets window.define (AMD) as non-configurable.
      // Instead of touching window.define (which breaks Monaco's python.js loading),
      // we fetch xterm scripts as text and execute them in a sandboxed scope where
      // 'define' and 'require' are shadowed as undefined, forcing UMD global export.
      if (!window.Terminal) {
        const loadScriptSandboxed = async (url) => {
          const resp = await fetch(url);
          if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url}`);
          const code = await resp.text();
          // Execute in a scope where define/require are undefined → forces global export
          (new Function('define', 'require', code))(undefined, undefined);
        };

        const cdns = [
          'https://unpkg.com/xterm@5.3.0/',
          'https://cdn.jsdelivr.net/npm/xterm@5.3.0/',
          'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/'
        ];
        let loaded = false;
        for (const base of cdns) {
          try {
            const isUnpkg = base.includes('unpkg');
            const isXtermNew = base.includes('@xterm/xterm');
            const cssUrl = isUnpkg ? `${base}css/xterm.css` : (isXtermNew ? `${base}css/xterm.css` : `${base}xterm.min.css`);
            const jsUrl = isUnpkg ? `${base}lib/xterm.js` : (isXtermNew ? `${base}lib/xterm.js` : `${base}xterm.min.js`);
            const fitUrl = isUnpkg 
              ? 'https://unpkg.com/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js' 
              : (isXtermNew 
                ? 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js'
                : 'https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js');

            loadCSS(cssUrl);
            await loadScriptSandboxed(jsUrl);
            await loadScriptSandboxed(fitUrl);
            loaded = true;
            console.log(`[AlgoLab] xterm loaded from ${base}`);
            break;
          } catch (e) { console.warn(`[AlgoLab] CDN ${base} failed:`, e.message); }
        }
        if (loaded) {
          let wait = 0;
          while (!(window.Terminal || window.Xterm) && wait < 50) {
            await new Promise(r => setTimeout(r, 100));
            wait++;
          }
          if (!window.Terminal && window.Xterm) window.Terminal = window.Xterm;
        }
      }
      
      if (window.Terminal) console.log('[AlgoLab] Terminal ready');
      else console.error('[AlgoLab] Terminal failed to load');
      setTerminalLoaded(true);

      // ===== STEP 2: Now start Monaco (define is safely restored) =====
      if (window.require) {
        window.require.config({
          paths: { 'vs': 'lib/monaco/vs' }
        });
      }

      const waitForMonaco = setInterval(() => {
        if (window.monaco && window.monaco.editor) {
          clearInterval(waitForMonaco);
          initMonacoWithObserver();
        } else if (window.require && !window.monaco) {
          try {
            window.require(['vs/editor/editor.main'], function() {});
          } catch (e) {}
        }
      }, 200);
      
      // Auto-clear after 20 seconds to prevent infinite loop
      setTimeout(() => {
        clearInterval(waitForMonaco);
        if (!window.monaco || !window.monaco.editor) {
          console.error('[AlgoLab] Monaco failed to load after 20s');
        }
      }, 20000);
    };
    setup();
    return () => {
      if (editorRef.current) { 
        console.log('[AlgoLab] Disposing editor on cleanup');
        editorRef.current.dispose(); 
        editorRef.current = null; 
      }
      setIsEditorReady(false);
    };
  }, [createMonacoEditor]);
  useEffect(() => {
    if (isOpen && !editorRef.current && window.monaco) {
      const timer = setTimeout(() => createMonacoEditor(), 200);
      return () => clearTimeout(timer);
    }
  }, [isOpen, createMonacoEditor]);
  // Safety net Effect: ensures editor is visible, has content and is laid out
  useEffect(() => {
    if (!isOpen) return;
    
    const interval = setInterval(() => {
      if (!editorRef.current) return;
      
      const container = editorContainerRef.current;
      if (container && container.offsetParent !== null) { // if visible
        const editor = editorRef.current;
        const domNode = editor.getDomNode();
        
        if (domNode) {
          const viewLines = domNode.querySelector('.view-lines');
          const isBlack = !viewLines || !viewLines.textContent || viewLines.textContent.trim().length === 0;
          
          if (isBlack && activeFileRef.current) {
            const content = fileContentsRef.current[activeFileRef.current.path];
            if (content) {
              if (!editor.getValue()) editor.setValue(content);
              editor.layout();
              forceElectronRepaint(editor);
            }
          }
        }
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [isOpen, forceElectronRepaint]);
  useEffect(() => {
    if (isReviewingDiff && window.monaco) {
      const container = diffEditorContainerRef.current;
      if (container && !diffEditorRef.current) {
        diffEditorRef.current = window.monaco.editor.createDiffEditor(container, {
          theme: 'vs-dark',
          automaticLayout: true,
          renderSideBySide: false,
          originalEditable: false,
          readOnly: false,
          fontSize: 14,
          fontFamily: 'JetBrains Mono'
        });
      }
      if (diffEditorRef.current && activeFile && previousContent) {
        const originalModel = window.monaco.editor.createModel(previousContent.content, 'python');
        const modifiedModel = window.monaco.editor.createModel(editorRef.current.getValue(), 'python');
        diffEditorRef.current.setModel({
          original: originalModel,
          modified: modifiedModel
        });
        return () => {
          originalModel.dispose();
          modifiedModel.dispose();
        };
      }
    }
  }, [isReviewingDiff, activeFile, previousContent]);
  useEffect(() => {
    console.log('[Terminal] Effect run. Open:', isTerminalOpen, 'Ref:', !!terminalContainerRef.current, 'Term:', !!window.Terminal, 'Loaded:', terminalLoaded);
    
    let term = null;
    let ws = null;
    let fitAddon = null;
    let resizeHandler = null;

    if (isTerminalOpen && terminalContainerRef.current && !xtermRef.current) {
      if (!window.Terminal) {
        terminalContainerRef.current.innerHTML = '<div style="color:#aaa;padding:20px;font-size:12px;font-family:monospace;">Waiting for Terminal library...</div>';
      } else {
        terminalContainerRef.current.innerHTML = '<div style="color:#aaa;padding:20px;font-size:12px;font-family:monospace;">Initializing Terminal...</div>';
      }
    }
    
    if (isTerminalOpen && terminalContainerRef.current && !xtermRef.current && window.Terminal) {
      console.log('[Terminal] Initializing...');
      try {
        term = new window.Terminal({
          theme: {
            background: '#111111',
            foreground: '#ffffff',
            cursor: '#00ff00',
            selectionBackground: 'rgba(255, 255, 255, 0.3)',
            black: '#000000',
            red: '#ff5555',
            green: '#55ff55',
            yellow: '#ffff55',
            blue: '#5555ff',
            magenta: '#ff55ff',
            cyan: '#55ffff',
            white: '#ffffff'
          },
          fontSize: 13,
          fontFamily: 'JetBrains Mono, Menlo, Monaco, Consolas, "Courier New", monospace',
          convertEol: true,
          cursorBlink: true,
          cursorStyle: 'block',
          scrollback: 1000,
          scrollOnUserInput: true
        });

        const FitAddonCtor = (window.FitAddon && window.FitAddon.FitAddon) || window.FitAddon;
        if (!FitAddonCtor) throw new Error('FitAddon library not found');
        
        fitAddon = new FitAddonCtor();
        term.loadAddon(fitAddon);
        term.open(terminalContainerRef.current);
        
        xtermRef.current = term;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws/terminal`);
        socketRef.current = ws;

        ws.onopen = () => {
          console.log('[Terminal] WS Connected');
          term.write('\x1b[1;32m[Connected to Backend]\x1b[0m\r\n');
        };

        ws.onmessage = (event) => {
          term.write(event.data);
        };

        ws.onerror = (error) => {
          console.error('[Terminal] WS Error:', error);
          term.write('\x1b[1;31m[Connection Error]\x1b[0m\r\n');
        };

        ws.onclose = (event) => {
          console.log('[Terminal] WS Closed:', event.code, event.reason);
          socketRef.current = null;
          term.write('\r\n\x1b[1;31m[Connection Closed]\x1b[0m\r\n');
        };

        term.onData((data) => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(data);
          }
        });

        term.onResize(({ cols, rows }) => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'resize', cols, rows }));
          }
        });

        resizeHandler = () => fitAddon.fit();
        window.addEventListener('resize', resizeHandler);
        
        // Initial fit
        setTimeout(() => {
          if (fitAddon) fitAddon.fit();
          term.focus();
        }, 500);

        console.log('[Terminal] Initialized and WS opened');

      } catch (err) {
        console.error('[Terminal] Critical failure:', err);
        if (terminalContainerRef.current) {
          terminalContainerRef.current.innerHTML = `<div style="color:#ff5555;padding:20px;font-size:12px;font-family:monospace;">Terminal Init Error: ${err.message}</div>`;
        }
      }
    }

    return () => {
      if (resizeHandler) window.removeEventListener('resize', resizeHandler);
      if (!isTerminalOpen && xtermRef.current) {
        if (socketRef.current) socketRef.current.close();
        xtermRef.current.dispose();
        xtermRef.current = null;
        socketRef.current = null;
      }
    };
  }, [isTerminalOpen, terminalHeight, isChatOpen, chatWidth, isSidebarOpen, sidebarWidth, terminalLoaded]);
  useEffect(() => {
    if (!isEditorReady || !editorRef.current) return;
    if (activeFile) {
      const content = fileContents[activeFile.path];
      if (content !== undefined) {
        const currentModel = editorRef.current.getModel();
        const currentVal = currentModel?.getValue();
        if (currentVal !== content) {
          setEditorContent(content, activeFile);
        } else {
          forceElectronRepaint(editorRef.current);
        }
      }
    } else {
      const currentModel = editorRef.current.getModel();
      if (currentModel?.getValue() !== '') {
        const emptyUri = window.monaco.Uri.parse('file:///empty');
        let emptyModel = window.monaco.editor.getModel(emptyUri);
        if (!emptyModel) {
          emptyModel = window.monaco.editor.createModel('', 'python', emptyUri);
        }
        editorRef.current.setModel(emptyModel);
      }
    }
  }, [isEditorReady, activeFile, fileContents, setEditorContent, forceElectronRepaint]);
  useEffect(() => {
    if (!isOpen || !isEditorReady || !editorRef.current) return;
    const attempts = [50, 200, 500, 1000];
    const timers = attempts.map((delay) =>
      setTimeout(() => {
        if (!editorRef.current) return;
        if (activeFile) {
          const content = fileContents[activeFile.path] ?? fileContentsRef.current[activeFile.path];
          if (content !== undefined) {
            const currentVal = editorRef.current.getValue();
            if (currentVal !== content) {
              setEditorContent(content, activeFile);
            } else {
              forceElectronRepaint(editorRef.current);
            }
          } else {
            forceElectronRepaint(editorRef.current);
          }
        } else {
          editorRef.current.layout();
        }
        if (pendingContentRef.current) {
          const pending = pendingContentRef.current;
          setEditorContent(pending.content, pending.file);
        }
      }, delay)
    );
    return () => timers.forEach(clearTimeout);
  }, [isOpen, isEditorReady, activeFile, fileContents, setEditorContent, forceElectronRepaint]);
  const fetchFiles = async () => {
    try {
      const resp = await fetch('/api/algolab/files');
      if (!resp.ok) {
        console.error('[AlgoLab] /api/algolab/files error:', resp.status);
        return;
      }
      const data = await resp.json();
      // Always guarantee arrays so .map() never crashes
      setFiles({
        indicators: Array.isArray(data?.indicators) ? data.indicators : [],
        strategies: Array.isArray(data?.strategies) ? data.strategies : [],
      });
    } catch (e) {
      console.error("Error fetching files:", e);
    }
  };
  useEffect(() => {
    const init = async () => {
      await fetchFiles();
      await fetchAiSettings();
      await fetchChatHistory();
      await fetchEditorState();
    };
    init();
  }, []);
  const fetchEditorState = async () => {
    try {
      const resp = await fetch('/api/algolab/state');
      const data = await resp.json();
      if (data) {
        if (data.open_files && data.open_files.length > 0) {
          setOpenFiles(data.open_files);
          setFileContents(data.file_contents);
          openFilesRef.current = data.open_files;
          fileContentsRef.current = data.file_contents;
          if (data.active_file_path) {
            const active = data.open_files.find((f) => f.path === data.active_file_path);
            if (active) {
              setActiveFile(active);
              activeFileRef.current = active;
            }
          }
        }
        if (data.is_chat_open !== undefined) {
          setIsChatOpen(data.is_chat_open);
          isChatOpenRef.current = data.is_chat_open;
        }
        if (data.chat_width) {
          setChatWidth(data.chat_width);
          chatWidthRef.current = data.chat_width;
        }
      }
    } catch (e) { console.error("Error fetching editor state:", e); }
  };
  const saveEditorState = useCallback(async (currentOpenFiles, currentContents, currentActive, chatOpen, currentChatWidth) => {
    try {
      await fetch('/api/algolab/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          open_files: currentOpenFiles,
          file_contents: currentContents,
          active_file_path: currentActive?.path,
          is_chat_open: chatOpen,
          chat_width: currentChatWidth
        })
      });
    } catch (e) { console.error("Error saving editor state:", e); }
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      saveEditorState(openFiles, fileContents, activeFile, isChatOpen, chatWidth);
    }, 800);
    return () => {
      clearTimeout(timer);
      if (openFilesRef.current) {
        saveEditorState(
          openFilesRef.current,
          fileContentsRef.current,
          activeFileRef.current,
          isChatOpenRef.current,
          chatWidthRef.current
        );
      }
    };
  }, [openFiles, fileContents, activeFile, isChatOpen, chatWidth, saveEditorState]);
  const fetchChatHistory = async () => {
    try {
      const resp = await fetch('/api/algolab/chat/history');
      const data = await resp.json();
      if (data) setChatMessages(data);
    } catch (e) { console.error("Error fetching chat history:", e); }
  };
  const clearChatHistory = async () => {
    setShowClearConfirm(true);
  };
  const handleConfirmClearChat = async () => {
    try {
      await fetch('/api/algolab/chat/history', { method: 'DELETE' });
      setChatMessages([]);
      setShowClearConfirm(false);
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'success', title: 'History Cleared', message: 'LLAMA QUANTUM memory has been cleared.' }
      }));
    } catch (e) { console.error("Error clearing chat history:", e); }
  };
  const fetchAiSettings = async () => {
    try {
      const resp = await fetch('/api/algolab/settings/ai');
      const data = await resp.json();
      if (data) setAiSettings(data);
    } catch (e) { console.error("Error fetching AI settings:", e); }
  };
  const saveAiSettings = async () => {
    try {
      const resp = await fetch('/api/algolab/settings/ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(aiSettings)
      });
      if (resp.ok) {
        setShowAiSettings(false);
        window.dispatchEvent(new CustomEvent('platform-notif', {
          detail: { type: 'success', title: 'Settings Saved', message: 'AI settings have been updated.' }
        }));
      }
    } catch (e) { console.error("Error saving AI settings:", e); }
  };
  const fetchAvailableModels = useCallback(async (provider) => {
    if (!provider) return;
    setIsFetchingModels(true);
    try {
      const resp = await fetch(`/api/algolab/models?provider=${provider}`);
      const data = await resp.json();
      if (Array.isArray(data)) {
        setAvailableModels(data);
      }
    } catch (e) { console.error("Error fetching models:", e); } finally { setIsFetchingModels(false); }
  }, []);
  useEffect(() => {
    if (showAiSettings) {
      fetchAvailableModels(aiSettings.provider);
    }
  }, [showAiSettings, aiSettings.provider, fetchAvailableModels]);
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages]);
  const handleEnhancePrompt = async () => {
    if (!inputMessage.trim() || isLoading) return;
    setIsLoading(true);
    try {
      const resp = await fetch('/api/algolab/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [
            { role: 'user', content: `Improve the following prompt to be more technical, detailed, and structured for a senior quantitative trading developer in Python. Keep the original language (Spanish). Respond ONLY with the improved prompt: "${inputMessage}"` }],
          agentic_mode: false
        })
      });
      if (!resp.ok) throw new Error('Failed to improve the prompt');
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let enhancedText = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.replace('data: ', '').trim();
            if (dataStr === '[DONE]') continue;
            try {
              const data = JSON.parse(dataStr);
              if (data.content) enhancedText += data.content;
            } catch (e) { }
          }
        }
      }
      if (enhancedText) setInputMessage(enhancedText.trim());
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };
  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;
    let currentSkill = null;
    let textToSend = inputMessage.trim();
    if (textToSend.startsWith('/skill')) {
      const parts = textToSend.split(' ');
      currentSkill = parts[1];
      textToSend = parts.slice(2).join(' ');
      if (!textToSend) {
        window.dispatchEvent(new CustomEvent('platform-notif', {
          detail: { type: 'warning', title: 'Skill Usage', message: 'Write your question after the /skill command.' }
        }));
        return;
      }
    }
    const newUserMessage = { role: 'user', content: textToSend };
    const newMessages = [...chatMessages, newUserMessage];
    setChatMessages(newMessages);
    setInputMessage('');
    setIsLoading(true);
    if (activeFile && editorRef.current) {
      setPreviousContent({ path: activeFile.path, content: editorRef.current.getValue() });
    }
    const aiPlaceholder = { role: 'assistant', content: '' };
    setChatMessages((prev) => [...prev, aiPlaceholder]);
    try {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      abortControllerRef.current = new AbortController();
      const resp = await fetch('/api/algolab/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          messages: newMessages,
          skill: currentSkill,
          active_file_path: activeFile?.path,
          agentic_mode: agenticMode
        })
      });
      if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.detail || 'Server error');
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = "";
      let buffer = "";
      let currentToolCall = null;
      let toolCallBuffer = { id: "", name: "", arguments: "" };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;
          const dataStr = trimmedLine.replace('data: ', '').trim();
          if (dataStr === '[DONE]') continue;
          try {
            const data = JSON.parse(dataStr);
            if (data.content) {
              accumulatedContent += data.content;
              if (agenticMode && activeFile && editorRef.current) {
                const matches = [...accumulatedContent.matchAll(/```(?:python|javascript)?\n([\s\S]*?)(?:```|$)/g)];
                if (matches.length > 0) {
                  const lastMatch = matches[matches.length - 1];
                  const extractedCode = lastMatch[1];
                  if (extractedCode !== undefined) {
                    setIsAiWriting(true);
                    editorRef.current.setValue(extractedCode);
                    const lineCount = editorRef.current.getModel().getLineCount();
                    editorRef.current.revealLine(lineCount);
                  }
                }
              }
              setChatMessages((prev) => {
                const updated = [...prev];
                const lastMsg = updated[updated.length - 1];
                if (lastMsg && lastMsg.role === 'assistant') {
                  updated[updated.length - 1] = {
                    role: 'assistant',
                    content: accumulatedContent
                  };
                }
                return updated;
              });
            }
            if (agenticMode && data.tool_call_chunk) {
              const { name, arguments: args, complete } = data.tool_call_chunk;
              if (name) toolCallBuffer.name = name;
              if (args) toolCallBuffer.arguments = args;
              if (toolCallBuffer.name === 'write_file' && toolCallBuffer.arguments) {
                let partialContent = null;
                let targetPath = null;
                try {
                  const parsedArgs = JSON.parse(toolCallBuffer.arguments);
                  targetPath = parsedArgs.path;
                  partialContent = parsedArgs.content;
                } catch (e) {
                  const pathMatch = toolCallBuffer.arguments.match(/"path"\s*:\s*"([^"]+)"/);
                  if (pathMatch) targetPath = pathMatch[1];
                  const contentStartIndex = toolCallBuffer.arguments.indexOf('"content"');
                  if (contentStartIndex !== -1) {
                    const afterContent = toolCallBuffer.arguments.substring(contentStartIndex + 9);
                    const firstQuote = afterContent.indexOf('"');
                    if (firstQuote !== -1) {
                      let contentPart = afterContent.substring(firstQuote + 1);
                      partialContent = contentPart.
                        replace(/\\n/g, '\n').
                        replace(/\\t/g, '\t').
                        replace(/\\"/g, '"').
                        replace(/\\\\/g, '\\');
                      if (partialContent.endsWith('"')) partialContent = partialContent.slice(0, -1);
                    }
                  }
                }
                if (targetPath && partialContent !== null) {
                  const isActiveFile = activeFile?.path === targetPath ||
                    activeFile?.path?.endsWith(targetPath) ||
                    targetPath?.endsWith(activeFile?.name || '---');
                  if (isActiveFile && editorRef.current) {
                    setIsAiWriting(true);
                    editorRef.current.setValue(partialContent);
                    const lineCount = editorRef.current.getModel().getLineCount();
                    editorRef.current.revealLine(lineCount);
                  }
                }
              }
              if (complete) {
                setIsAiWriting(false);
                toolCallBuffer = { id: "", name: "", arguments: "" };
              }
            }
            if (data.agent_actions) {
              setIsAiWriting(false);
              const { files_updated, run_triggered } = data.agent_actions;
              if (files_updated && files_updated.length > 0) {
                files_updated.forEach((update) => {
                  setFileContents((prev) => ({ ...prev, [update.path]: update.content }));
                  if (!agenticMode && activeFile?.path === update.path && editorRef.current) {
                    editorRef.current.setValue(update.content);
                  }
                });
                fetchFiles();
              }
              if (run_triggered && activeFile) {
                handleRun();
              }
            }
            if (data.error) {
              throw new Error(data.error);
            }
          } catch (err) {
            console.warn("Error parsing chunk:", err, dataStr);
            if (dataStr.includes('"error":')) throw err;
          }
        }
      }
    } catch (e) {
      console.error("AI Error:", e);
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'error', title: 'AI Error', message: e.message || 'Error communicating with the AI.' }
      }));
      setChatMessages((prev) => prev.filter((m) => m.content !== '' || m.role === 'user'));
    } finally {
      setIsLoading(false);
      setIsAiWriting(false);
      // Auto-trigger Review Mode if code was written and is different
      if (previousContent && activeFile && editorRef.current) {
        const currentVal = editorRef.current.getValue();
        if (currentVal !== previousContent.content) {
          setIsReviewingDiff(true);
        }
      }
    }
  };
  const applyAiCode = (code) => {
    if (editorRef.current && activeFile) {
      const model = editorRef.current.getModel();
      setPreviousContent({ path: activeFile.path, content: model.getValue() });
      const fullRange = model.getFullModelRange();
      editorRef.current.executeEdits("ai-assistant", [{
        range: fullRange,
        text: code,
        forceMoveMarkers: true
      }]);
      editorRef.current.layout();
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'success', title: 'Code Updated', message: 'The file has been synced with the Agent.' }
      }));
    }
  };
  const handleUndoAi = () => {
    if (previousContent && editorRef.current && activeFile && activeFile.path === previousContent.path) {
      editorRef.current.setValue(previousContent.content);
      setPreviousContent(null);
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'info', title: 'Change Reverted', message: 'The previous code version has been restored.' }
      }));
    }
  };
  const handleSyncLayout = () => {
    if (editorRef.current) {
      editorRef.current.layout();
      if (diffEditorRef.current) diffEditorRef.current.layout();
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'success', title: 'Editor Synced', message: 'The editor layout has been refreshed manually.' }
      }));
    }
  };
  const handleAcceptDiff = () => {
    setIsReviewingDiff(false);
    setPreviousContent(null);
    window.dispatchEvent(new CustomEvent('platform-notif', {
      detail: { type: 'success', title: 'Changes Accepted', message: 'The new code version has been applied.' }
    }));
  };
  const handleRejectDiff = () => {
    if (previousContent && editorRef.current) {
      editorRef.current.setValue(previousContent.content);
      setIsReviewingDiff(false);
      setPreviousContent(null);
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'info', title: 'Changes Rejected', message: 'The original code has been restored.' }
      }));
    }
  };
  const loadFile = async (file) => {
    if (activeFile?.path === file.path) {
      if (editorRef.current) {
        const currentVal = editorRef.current.getValue();
        if (!currentVal && fileContents[file.path]) {
          setEditorContent(fileContents[file.path], file);
        } else {
          forceElectronRepaint(editorRef.current);
        }
      }
      return;
    }
    if (activeFile && editorRef.current) {
      const currentVal = editorRef.current.getValue();
      setFileContents((prev) => {
        const next = { ...prev, [activeFile.path]: currentVal };
        fileContentsRef.current = next;
        return next;
      });
    }
    const isAlreadyOpen = openFiles.find((f) => f.path === file.path);
    if (isAlreadyOpen) {
      setActiveFile(file);
      activeFileRef.current = file;
      const nextContent = fileContents[file.path] ?? fileContentsRef.current[file.path];
      if (nextContent !== undefined) {
        setTimeout(() => setEditorContent(nextContent, file), 0);
      }
      return;
    }
    setIsLoading(true);
    try {
      const resp = await fetch('/api/algolab/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: file.path })
      });
      const data = await resp.json();
      if (resp.ok && data.content !== undefined) {
        const newContents = { ...fileContentsRef.current, [file.path]: data.content };
        fileContentsRef.current = newContents;
        setOpenFiles((prev) => {
          const next = [...prev, file];
          openFilesRef.current = next;
          return next;
        });
        setFileContents(newContents);
        setActiveFile(file);
        activeFileRef.current = file;
        setEditorContent(data.content, file);
      }
    } catch (e) {
      console.error("Error loading file:", e);
    } finally {
      setIsLoading(false);
    }
  };
  const switchTab = (file) => {
    if (activeFile?.path === file.path) return;
    if (activeFile && editorRef.current) {
      const currentVal = editorRef.current.getValue();
      setFileContents((prev) => {
        const next = { ...prev, [activeFile.path]: currentVal };
        fileContentsRef.current = next;
        return next;
      });
    }
    setActiveFile(file);
    activeFileRef.current = file;
    const nextContent = fileContents[file.path] ?? fileContentsRef.current[file.path];
    if (nextContent !== undefined) {
      setTimeout(() => setEditorContent(nextContent, file), 0);
    }
  };
  const handleCloseFile = (e, fileToClose) => {
    if (e) e.stopPropagation();
    const newOpenFiles = openFiles.filter((f) => f.path !== fileToClose.path);
    const newContents = { ...fileContents };
    delete newContents[fileToClose.path];
    openFilesRef.current = newOpenFiles;
    fileContentsRef.current = newContents;
    setOpenFiles(newOpenFiles);
    setFileContents(newContents);
    if (activeFile?.path === fileToClose.path) {
      let nextActive = null;
      if (newOpenFiles.length > 0) {
        nextActive = newOpenFiles[newOpenFiles.length - 1];
        setActiveFile(nextActive);
        activeFileRef.current = nextActive;
      } else {
        setActiveFile(null);
        activeFileRef.current = null;
      }
      saveEditorState(newOpenFiles, newContents, nextActive, isChatOpen, chatWidth);
    } else {
      saveEditorState(newOpenFiles, newContents, activeFile, isChatOpen, chatWidth);
    }
  };
  const handleSave = async () => {
    if (!activeFile) return;
    setIsLoading(true);
    const content = editorRef.current && !showFallback ?
      editorRef.current.getValue() :
      fallbackContentRef.current ?? fileContentsRef.current[activeFile.path] ?? '';
    try {
      const resp = await fetch('/api/algolab/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: activeFile.path, content })
      });
      if (resp.ok) {
        setFileContents((prev) => ({ ...prev, [activeFile.path]: content }));
        window.dispatchEvent(new CustomEvent('platform-notif', {
          detail: { type: 'success', title: 'Saved', message: `${activeFile.name} changes saved.` }
        }));
      }
    } catch (e) { console.error("Error saving file:", e); } finally { setIsLoading(false); }
  };
  const handleDeleteFile = async () => {
    if (!fileToDelete) return;
    try {
      const resp = await fetch(`/api/algolab/files?path=${encodeURIComponent(fileToDelete.path)}`, {
        method: 'DELETE'
      });
      if (resp.ok) {
        window.dispatchEvent(new CustomEvent('platform-notif', {
          detail: { type: 'success', title: 'File Deleted', message: `The file ${fileToDelete.name} has been deleted.` }
        }));
        handleCloseFile(null, fileToDelete);
        await fetchFiles();
      }
    } catch (e) { console.error("Error deleting file:", e); }
    setFileToDelete(null);
  };
  const handleRenameFile = async () => {
    if (!contextMenu.file || !renameName) return;
    try {
      const resp = await fetch('/api/algolab/files/rename', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_path: contextMenu.file.path, new_name: renameName })
      });
      const data = await resp.json();
      if (resp.ok) {
        window.dispatchEvent(new CustomEvent('platform-notif', {
          detail: { type: 'success', title: 'Renamed', message: `File renamed to ${renameName}` }
        }));
        setOpenFiles((prev) => prev.map((f) => f.path === contextMenu.file.path ? { ...f, name: data.new_path.split(/[\\/]/).pop(), path: data.new_path } : f));
        if (activeFile?.path === contextMenu.file.path) {
          setActiveFile((prev) => ({ ...prev, name: data.new_path.split(/[\\/]/).pop(), path: data.new_path }));
        }
        await fetchFiles();
      }
    } catch (e) { console.error("Error renaming file:", e); }
    setShowRenameModal(false);
    setRenameName('');
  };
  const handleContextMenu = (e, file) => {
    e.preventDefault();
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      file
    });
  };
  useEffect(() => {
    const handleClick = () => setContextMenu({ ...contextMenu, visible: false });
    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, [contextMenu]);
  const logToTerminal = (message, type = 'info') => {
    if (!xtermRef.current) return;
    const timestamp = new Date().toLocaleTimeString();
    let color = '\x1b[37m';
    if (type === 'success') color = '\x1b[1;32m';
    if (type === 'error') color = '\x1b[1;31m';
    if (type === 'warning') color = '\x1b[1;33m';
    if (type === 'system') color = '\x1b[1;36m';
    const reset = '\x1b[0m';
    const gray = '\x1b[90m';
    xtermRef.current.writeln(`${gray}[${timestamp}]${reset} ${color}${message}${reset}`);
  };
  const handleRun = async () => {
    if (!activeFile) return;
    setIsTerminalOpen(true);
    // Force a small delay to ensure container is ready
    setTimeout(() => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        const cmd = `python "${activeFile.path}"\r`;
        socketRef.current.send(cmd);
      } else if (xtermRef.current) {
        xtermRef.current.writeln('\x1b[1;33m[Retrying connection...]\x1b[0m');
        // If not connected, maybe we should re-trigger the effect?
        setTerminalLoaded(prev => !prev); // Toggle to trigger useEffect
        setTimeout(() => {
           if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
             const cmd = `python "${activeFile.path}"\r`;
             socketRef.current.send(cmd);
           }
        }, 1000);
      }
    }, 800);
  };
  const handleCompileAndDeploy = async () => {
    if (!activeFile) return;
    if (!isTerminalOpen) setIsTerminalOpen(true);
    logToTerminal(`Compiling ${activeFile.name}...`, 'system');
    try {
      const content = editorRef.current.getValue();
      const resp = await fetch('/api/algolab/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: activeFile.path,
          content: content
        })
      });
      const data = await resp.json();
      if (resp.ok) {
        logToTerminal(`✅ Compilation Successful: ${data.name}`, 'success');
        logToTerminal(`   Type: ${data.type}`, 'info');
        window.dispatchEvent(new CustomEvent('platform-notif', {
          detail: {
            type: 'success',
            title: '✅ Compiled and Activated',
            message: `${data.type === 'strategy' ? 'Strategy' : 'Indicator'} "${data.name}" is ready to use on the platform.`
          }
        }));
        if (window.refreshIndicators) window.refreshIndicators();
        fetchFiles();
      } else {
        logToTerminal(`❌ Compilation Error: ${data.detail || 'Unknown'}`, 'error');
        if (data.detail && (data.detail.includes("ModuleNotFoundError") || data.detail.includes("ImportError"))) {
          logToTerminal(`⚠️ Missing dependencies detected. Starting scan...`, 'warning');
          checkDependencies();
        }
        throw new Error(data.detail || 'Failed to compile');
      }
    } catch (e) {
      logToTerminal(`❌ Exception: ${e.message}`, 'error');
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'error', title: 'Compilation Error', message: e.message }
      }));
    }
  };
  const checkDependencies = async () => {
    if (!activeFile) return;
    setIsLoading(true);
    if (!isTerminalOpen) setIsTerminalOpen(true);
    logToTerminal("🔍 Analyzing dependencies...", 'system');
    try {
      const content = editorRef.current.getValue();
      const resp = await fetch('/api/algolab/dependencies/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: content, path: activeFile.path })
      });
      const data = await resp.json();
      if (data.missing && data.missing.length > 0) {
        logToTerminal(`⚠️ Missing libraries detected: ${data.missing.join(', ')}`, 'warning');
        setMissingDependencies(data.missing);
        setShowDependencyModal(true);
      } else {
        if (data.error) {
          logToTerminal(`❌ Analysis error: ${data.error}`, 'error');
        } else {
          logToTerminal("✅ All dependencies are satisfied.", 'success');
          window.dispatchEvent(new CustomEvent('platform-notif', {
            detail: { type: 'success', title: 'Dependencies OK', message: 'All libraries are installed.' }
          }));
        }
      }
    } catch (e) {
      logToTerminal(`❌ Fatal analysis error: ${e.message}`, 'error');
      console.error("Error checking dependencies:", e);
    } finally {
      setIsLoading(false);
    }
  };
  const handleInstallDependencies = async () => {
    setIsInstallingDeps(true);
    logToTerminal(`📦 Installing: ${missingDependencies.join(', ')}...`, 'system');
    try {
      const resp = await fetch('/api/algolab/dependencies/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packages: missingDependencies })
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        logToTerminal(`✅ Installation completed successfully.`, 'success');
        setShowDependencyModal(false);
        setMissingDependencies([]);
        window.dispatchEvent(new CustomEvent('platform-notif', {
          detail: { type: 'success', title: 'Installation Complete', message: 'Libraries have been installed correctly. Try compiling again.' }
        }));
      } else {
        logToTerminal(`❌ Installation error: ${data.message || 'Unknown'}`, 'error');
        throw new Error(data.message || "Installation error");
      }
    } catch (e) {
      logToTerminal(`❌ Critical failure: ${e.message}`, 'error');
      window.dispatchEvent(new CustomEvent('platform-notif', {
        detail: { type: 'error', title: 'Installation Error', message: e.message }
      }));
    } finally {
      setIsInstallingDeps(false);
    }
  };
  const startResizing = useCallback((e) => {
    e.preventDefault();
    isResizingTerminal.current = true;
    document.body.style.cursor = 'ns-resize';
  }, []);
  const startSidebarResizing = useCallback((e) => {
    e.preventDefault();
    isResizingSidebar.current = true;
    document.body.style.cursor = 'ew-resize';
  }, []);
  const stopResizing = useCallback(() => {
    isResizingTerminal.current = false;
    isResizingSidebar.current = false;
    isResizingChat.current = false;
    document.body.style.cursor = 'default';
  }, []);
  const startChatResizing = useCallback((e) => {
    e.preventDefault();
    isResizingChat.current = true;
    document.body.style.cursor = 'ew-resize';
  }, []);
  const handleResizing = useCallback((e) => {
    if (isResizingTerminal.current) {
      const newHeight = window.innerHeight - e.clientY;
      if (newHeight >= 100 && newHeight <= window.innerHeight * 0.7) {
        setTerminalHeight(newHeight);
        if (window.FitAddon && xtermRef.current) {
          const fitAddon = new window.FitAddon.FitAddon();
          xtermRef.current.loadAddon(fitAddon);
          fitAddon.fit();
        }
      }
    }
    if (isResizingSidebar.current) {
      const newWidth = e.clientX - 48;
      if (newWidth >= 150 && newWidth <= 600) {
        setSidebarWidth(newWidth);
      }
    }
    if (isResizingChat.current) {
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth >= 200 && newWidth <= 800) {
        setChatWidth(newWidth);
      }
    }
  }, []);
  const handleCreateFile = async () => {
    if (!newFileName) return;
    try {
      const resp = await fetch('/api/algolab/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newFileName, type: newFileType })
      });
      const data = await resp.json();
      if (resp.ok) {
        window.dispatchEvent(new CustomEvent('notify', {
          detail: { type: 'success', title: 'File Created', message: `The file ${data.name} has been created successfully.` }
        }));
        await fetchFiles();
        loadFile({ name: data.name, path: data.path, type: newFileType });
      }
    } catch (e) { console.error("Error creating file:", e); }
    setShowNewFileModal(false);
    setNewFileName('');
  };
  return (
    React.createElement("div", { className: "flex w-full flex-1 h-full bg-bg overflow-hidden animate-in fade-in duration-500", onMouseMove: handleResizing, onMouseUp: stopResizing },
      React.createElement("div", { className: "w-12 border-r border-border bg-black/40 flex flex-col items-center py-4 gap-4 shrink-0" },
        React.createElement("button", {
          onClick: () => { setIsSidebarOpen(!isSidebarOpen); },
          className: `p-2 transition-all ${isSidebarOpen ? 'text-accent' : 'text-muted hover:text-white'}`
        },
          React.createElement("i", { className: "fas fa-file-code text-lg" })
        ),
        React.createElement("button", {
          onClick: () => { setIsChatOpen(!isChatOpen); },
          className: `p-2 transition-all flex items-center justify-center ${isChatOpen ? 'bg-accent/10 border border-accent/20 rounded-lg shadow-[0_0_10px_rgba(255,255,255,0.1)]' : 'opacity-50 hover:opacity-100 hover:scale-110'}`,
          title: "LLAMA QUANTUM AI"
        },
          React.createElement("img", { src: "/images/agentellama.png", className: `w-6 h-6 object-contain ${isChatOpen ? '' : 'grayscale'}` })
        ),
        React.createElement("div", { className: "flex-1" }),
        React.createElement("button", {
          onClick: () => setShowAiSettings(true),
          className: "p-2 text-muted hover:text-accent transition-all"
        },
          React.createElement("i", { className: "fas fa-cog text-lg" })
        )
      ),
      React.createElement("div", {
        style: { width: isSidebarOpen ? sidebarWidth : 0 },
        className: `border-r border-border bg-panel flex flex-col transition-all duration-300 relative group min-w-0 ${!isSidebarOpen ? 'overflow-hidden border-none' : ''}`
      },
        React.createElement("div", { className: "p-4 border-b border-border flex justify-between items-center bg-black/20 shrink-0" },
          React.createElement("h2", { className: "text-xs font-bold tracking-widest text-accent uppercase flex items-center gap-2" },
            React.createElement("i", { className: "fas fa-folder-open" }), " EXPLORADOR"
          ),
          React.createElement("button", { onClick: fetchFiles, className: "text-muted hover:text-white transition-colors" },
            React.createElement("i", { className: "fas fa-sync-alt text-[10px]" })
          )
        ),
        React.createElement("div", { className: "flex-1 overflow-y-auto p-2 space-y-4" },
          React.createElement("div", null,
            React.createElement("div", { className: "text-[10px] font-bold text-muted mb-2 px-2 uppercase tracking-tighter" }, "INDICATORS"),
            React.createElement("div", { className: "space-y-1" },
              (files.indicators || []).map((f) =>
                React.createElement("div", { key: f.path, className: "group flex flex-col" },
                  React.createElement("button", {
                    onClick: () => loadFile(f),
                    onContextMenu: (e) => handleContextMenu(e, f),
                    className: `w-full text-left px-3 py-1.5 rounded text-[11px] transition-all flex items-center justify-between ${activeFile?.path === f.path ? 'bg-accent/10 text-accent border-l-2 border-accent font-bold' : 'text-text/70 hover:bg-white/5 hover:text-white'}`,
                    title: f.metadata?.description || ''
                  },
                    React.createElement("div", { className: "flex items-center gap-2 overflow-hidden" },
                      React.createElement("i", { className: "fas fa-chart-line text-accent opacity-70" }),
                      React.createElement("span", { className: "truncate" }, f.name)
                    ),
                    f.metadata?.category &&
                    React.createElement("span", { className: "px-1 py-0.5 bg-accent/20 text-accent text-[8px] rounded uppercase font-bold shrink-0" }, f.metadata.category),
                    f.metadata?.name &&
                    React.createElement("i", { className: "fas fa-check-circle text-[9px] text-success ml-1", title: "Compiled and Ready" })
                  )
                )
              )
            )
          ),
          React.createElement("div", null,
            React.createElement("div", { className: "text-[10px] font-bold text-muted mb-2 px-2 uppercase tracking-tighter" }, "STRATEGIES"),
            React.createElement("div", { className: "space-y-1" },
              (files.strategies || []).map((f) =>
                React.createElement("div", { key: f.path, className: "group flex flex-col" },
                  React.createElement("button", {
                    onClick: () => loadFile(f),
                    onContextMenu: (e) => handleContextMenu(e, f),
                    className: `w-full text-left px-3 py-1.5 rounded text-[11px] transition-all flex items-center justify-between ${activeFile?.path === f.path ? 'bg-amber-500/10 text-amber-500 border-l-2 border-amber-500 font-bold' : 'text-text/70 hover:bg-white/5 hover:text-white'}`,
                    title: f.metadata?.description || ''
                  },
                    React.createElement("div", { className: "flex items-center gap-2 overflow-hidden" },
                      React.createElement("i", { className: "fab fa-python text-amber-500 opacity-70" }),
                      React.createElement("span", { className: "truncate" }, f.name)
                    ),
                    f.metadata?.category &&
                    React.createElement("span", { className: "px-1 py-0.5 bg-amber-500/20 text-amber-500 text-[8px] rounded uppercase font-bold shrink-0" }, f.metadata.category),
                    f.metadata?.name &&
                    React.createElement("i", { className: "fas fa-check-circle text-[9px] text-success ml-1", title: "Compiled and Ready" })
                  )
                )
              )
            )
          )
        ),
        React.createElement("div", { className: "p-4 border-t border-border shrink-0" },
          React.createElement("button", {
            onClick: () => setShowNewFileModal(true),
            className: "w-full bg-accent/10 border border-accent/30 text-accent hover:bg-accent hover:text-black transition-all py-2 rounded text-[10px] font-bold uppercase"
          },
            React.createElement("i", { className: "fas fa-plus mr-2" }), " New File"
          )
        ),
        isSidebarOpen &&
        React.createElement("div", {
          onMouseDown: startSidebarResizing,
          className: "absolute top-0 -right-1 bottom-0 w-2 cursor-ew-resize hover:bg-accent/30 transition-colors z-[60]"
        }
        )
      ),
      React.createElement("div", { className: "flex-1 flex flex-col bg-panel min-w-0" },
        React.createElement("div", { className: "h-10 border-b border-border flex items-center justify-between bg-black/40 overflow-hidden shrink-0" },
          React.createElement("div", { className: "flex items-center h-full gap-1 px-2 max-w-[80%] overflow-x-auto scrollbar-hide no-scrollbar" },
            React.createElement("button", {
              onClick: () => setIsSidebarOpen(!isSidebarOpen),
              className: `h-8 w-8 min-w-[32px] rounded flex items-center justify-center transition-all mr-1 ${isSidebarOpen ? 'text-accent bg-accent/10' : 'text-muted hover:text-white hover:bg-white/5'}`
            },
              React.createElement("i", { className: `fas ${isSidebarOpen ? 'fa-indent' : 'fa-outdent'} text-xs` })
            ),
            openFiles.map((file) =>
              React.createElement("div", {
                key: file.path,
                onClick: () => switchTab(file),
                className: `flex items-center gap-2 px-3 h-8 rounded-t border-t border-x transition-all cursor-pointer min-w-[120px] max-w-[200px] shrink-0 truncate ${activeFile?.path === file.path ? 'bg-panel border-border text-accent z-10' : 'bg-transparent border-transparent text-muted hover:bg-white/5 hover:text-white'}`
              },
                React.createElement("i", { className: "fab fa-python text-[10px] opacity-70" }),
                React.createElement("span", { className: "text-[10px] font-mono truncate flex-1" }, file.name),
                React.createElement("button", {
                  onClick: (e) => handleCloseFile(e, file),
                  className: "hover:text-red-500 transition-colors p-0.5 opacity-50 hover:opacity-100"
                },
                  React.createElement("i", { className: "fas fa-times text-[9px]" })
                )
              )
            ),
            openFiles.length === 0 &&
            React.createElement("span", { className: "px-2 text-[10px] text-muted italic" }, "No files open")
          ),
          React.createElement("div", { className: "flex items-center gap-1.5 pr-2 shrink-0" },
            activeFile &&
            React.createElement(React.Fragment, null,
              React.createElement("button", {
                onClick: handleRun, disabled: isRunning,
                className: `w-7 h-7 flex items-center justify-center rounded border border-border/50 transition-all ${isRunning ? 'text-muted' : 'text-accent hover:bg-accent/10 hover:border-accent/40'}`,
                title: "Run Python"
              },
                React.createElement("i", { className: `fas ${isRunning ? 'fa-spinner fa-spin' : 'fa-play'} text-[10px]` })
              ),
              React.createElement("button", {
                onClick: handleSave,
                className: "w-7 h-7 flex items-center justify-center text-success border border-border/50 hover:bg-success/10 hover:border-success/40 rounded transition-all",
                title: "Save"
              },
                React.createElement("i", { className: "fas fa-save text-[10px]" })
              ),
              previousContent && activeFile && activeFile.path === previousContent.path &&
              React.createElement(React.Fragment, null,
                React.createElement("button", {
                  onClick: () => setIsReviewingDiff(!isReviewingDiff),
                  className: `h-7 px-2.5 flex items-center gap-1.5 border rounded-lg transition-all text-[9px] font-bold tracking-tight uppercase ${isReviewingDiff ? 'bg-amber-500 text-black border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.3)]' : 'bg-amber-500/5 hover:bg-amber-500/10 text-amber-500 border-amber-500/20'}`,
                  title: "Review AI changes (Comparison)"
                },
                  React.createElement("i", { className: `fas ${isReviewingDiff ? 'fa-eye-slash' : 'fa-eye'} text-[9px]` }), isReviewingDiff ? 'CLOSE DIFF' : 'REVIEW CHANGES'
                ),
                React.createElement("button", {
                  onClick: handleUndoAi,
                  className: "h-7 px-2.5 flex items-center gap-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg transition-all text-[9px] font-bold uppercase",
                  title: "Undo AI changes (Revert)"
                },
                  React.createElement("i", { className: "fas fa-undo-alt" }), "UNDO"
                )
              ),
              React.createElement("button", {
                onClick: handleSyncLayout,
                className: "w-7 h-7 flex items-center justify-center text-muted hover:text-white border border-border/50 hover:bg-white/5 rounded transition-all",
                title: "Sync Layout"
              },
                React.createElement("i", { className: "fas fa-sync-alt text-[10px]" })
              ),
              React.createElement("button", {
                onClick: checkDependencies,
                className: "h-7 px-2.5 flex items-center gap-2 bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/20 hover:text-white rounded text-[9px] font-bold transition-all tracking-wider uppercase",
                title: "Check and fix dependencies"
              },
                React.createElement("i", { className: "fas fa-hammer text-[9px]" }), " DEPS"
              ),
              React.createElement("button", {
                onClick: () => fetchFiles(),
                className: "h-7 w-7 flex items-center justify-center bg-white/5 hover:bg-white/10 rounded text-muted hover:text-white transition-all",
                title: "Reload files"
              },
                React.createElement("i", { className: "fas fa-sync-alt text-[10px]" })
              ),
              React.createElement("button", {
                onClick: handleCompileAndDeploy,
                className: "h-7 px-2.5 flex items-center gap-2 bg-blue-500/10 border border-blue-500/30 text-blue-400 hover:bg-blue-500/20 hover:text-white rounded text-[9px] font-bold transition-all tracking-wider uppercase",
                title: "Compile and Activate"
              },
                React.createElement("i", { className: "fas fa-rocket text-[9px]" }), " COMPILE"
              )
            ),
            React.createElement("div", { className: "w-[1px] h-4 bg-border/50 mx-1" }),
            React.createElement("button", {
              onClick: () => setIsTerminalOpen(!isTerminalOpen),
              className: `w-7 h-7 flex items-center justify-center rounded transition-all ${isTerminalOpen ? 'text-accent bg-accent/10 border border-accent/30' : 'text-muted hover:text-white'}`,
              title: "Terminal"
            },
              React.createElement("i", { className: "fas fa-terminal text-xs" })
            )
          )
        ),
        React.createElement("div", { className: "flex-1 flex flex-col relative overflow-hidden" },
          React.createElement("div", { className: "flex-1 relative" },
            isAiWriting &&
            React.createElement("div", { className: "absolute top-4 right-8 z-[50] flex items-center gap-2 bg-accent/20 border border-accent/40 backdrop-blur-md px-3 py-1.5 rounded-full shadow-2xl animate-pulse" },
              React.createElement("div", { className: "w-2 h-2 bg-accent rounded-full animate-bounce" }),
              React.createElement("span", { className: "text-[10px] font-bold text-accent tracking-widest uppercase italic" }, "AI WRITING...")
            ),
            isReviewingDiff &&
            React.createElement("div", { className: "absolute top-6 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-6 bg-[#0f0f11]/95 border border-white/10 backdrop-blur-2xl px-8 py-3 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.8),0_0_20px_rgba(245,158,11,0.1)] animate-in slide-in-from-top duration-300 ring-1 ring-white/5" },
              React.createElement("div", { className: "flex items-center gap-3" },
                React.createElement("div", { className: "w-8 h-8 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center" },
                  React.createElement("i", { className: "fas fa-robot text-amber-500 text-xs" })
                ),
                React.createElement("div", { className: "flex flex-col" },
                  React.createElement("span", { className: "text-[9px] font-black text-amber-500 tracking-[0.2em] uppercase italic" }, "Quantum Review"),
                  React.createElement("span", { className: "text-[10px] text-white/80 font-bold" }, activeFile?.name)
                )
              ),
              React.createElement("div", { className: "w-[1px] h-8 bg-white/10 mx-1" }),
              React.createElement("div", { className: "flex items-center gap-3" },
                React.createElement("button", { onClick: handleRejectDiff, className: "h-9 px-5 flex items-center gap-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-xl transition-all text-[10px] font-black uppercase tracking-wider group" },
                  React.createElement("i", { className: "fas fa-times group-hover:rotate-90 transition-transform" }), "Discard"
                ),
                React.createElement("button", { onClick: handleAcceptDiff, className: "h-9 px-5 flex items-center gap-2 bg-emerald-500 text-black hover:bg-emerald-400 rounded-xl transition-all text-[10px] font-black uppercase tracking-wider shadow-[0_0_20px_rgba(16,185,129,0.2)]" },
                  React.createElement("i", { className: "fas fa-check" }), "Apply Changes"
                )
              )
            ),
            React.createElement("div", {
              ref: editorContainerRef, id: "monaco-editor-container",
              className: `absolute inset-0 ${isReviewingDiff || showFallback ? 'invisible' : 'visible'}`,
              onMouseEnter: () => {
                if (editorRef.current) {
                  editorRef.current.layout();
                }
              }
            }
            ),
            showFallback && activeFile && !isReviewingDiff &&
            React.createElement(React.Fragment, null,
              React.createElement("div", { className: "absolute top-3 right-4 z-[230] px-2 py-1 text-[9px] font-bold rounded bg-black/10 text-gray-700 border border-black/10" }, "Fallback"
              ),
              React.createElement("div", {
                ref: fallbackEditorRef,
                contentEditable: true,
                suppressContentEditableWarning: true,
                className: "absolute inset-0 z-[220] font-mono text-[12px] p-4 outline-none overflow-auto fallback-editor",
                style: { background: '#141414', color: '#e2e8f0', whiteSpace: 'pre', paddingRight: '44px' },
                onScroll: updateFallbackScroll,
                onInput: () => {
                  const el = fallbackEditorRef.current;
                  if (!el) return;
                  caretOffsetRef.current = getCaretOffset(el);
                  const next = el.textContent ?? '';
                  setFallbackContent(next);
                  fallbackContentRef.current = next;
                  setFileContents((prev) => {
                    const updated = { ...prev, [activeFile.path]: next };
                    fileContentsRef.current = updated;
                    return updated;
                  });
                  updateFallbackScroll();
                }
              }
              ),
              React.createElement("div", { className: "absolute top-0 right-0 bottom-0 w-8 z-[225] pointer-events-none", style: { background: 'linear-gradient(180deg, rgba(20,20,20,0.95), rgba(20,20,20,0.85))' } },
                fallbackScroll.visible &&
                React.createElement("div", { style: { position: 'absolute', right: '6px', width: '6px', borderRadius: '6px', background: '#5a5a5a', top: `${fallbackScroll.top}px`, height: `${fallbackScroll.height}px` } })
              )
            ),
            React.createElement("div", { ref: diffEditorContainerRef, id: "monaco-diff-editor-container", className: `absolute inset-0 ${isReviewingDiff ? 'visible' : 'invisible'}` }),
            !activeFile &&
            React.createElement("div", { className: "absolute inset-0 flex flex-col items-center justify-center bg-panel pointer-events-none z-10" },
              React.createElement("img", { src: "/images/QuantumLLama.png", className: "w-32 h-32 opacity-10 mb-6 grayscale" }),
              React.createElement("h3", { className: "text-muted text-sm font-medium tracking-widest" }, "QuantumLlama IDE"),
              React.createElement("p", { className: "text-[10px] text-muted/50 mt-2 uppercase tracking-[0.3em]" }, "Professional Algorithm Editor")
            )
          ),
          isTerminalOpen &&
          React.createElement("div", { style: { height: terminalHeight }, className: "border-t border-border bg-black flex flex-col relative shrink-0" },
            React.createElement("div", {
              onMouseDown: startResizing,
              className: "absolute -top-1 left-0 right-0 h-2 cursor-ns-resize hover:bg-accent/30 transition-colors z-[100]"
            }
            ),
            React.createElement("div", { className: "h-8 border-b border-border/50 flex items-center justify-between px-4 bg-white/5 shrink-0" },
              React.createElement("div", { className: "text-[10px] font-bold text-accent/80 flex items-center gap-2" },
                React.createElement("i", { className: "fas fa-terminal text-[9px]" }), " INTERACTIVE TERMINAL (PS)"
              ),
              React.createElement("div", { className: "flex items-center gap-2" },
                React.createElement("button", { onClick: () => xtermRef.current?.clear(), className: "text-muted hover:text-white p-1" },
                  React.createElement("i", { className: "fas fa-ban text-[10px]" })
                ),
                React.createElement("button", { onClick: () => setIsTerminalOpen(false), className: "text-muted hover:text-white p-1" },
                  React.createElement("i", { className: "fas fa-times text-[10px]" })
                )
              )
            ),
            React.createElement("div", { ref: terminalContainerRef, className: "flex-1 xterm-container p-2" })
          )
        )
      ),
      React.createElement("div", {
        style: { width: isChatOpen ? chatWidth : 0 },
        className: `border-l border-border bg-panel flex flex-col transition-all duration-300 relative group min-w-0 ${!isChatOpen ? 'overflow-hidden border-none' : ''}`
      },
        React.createElement("div", { className: "p-4 border-b border-border flex justify-between items-center bg-black/20 shrink-0" },
          React.createElement("div", { className: "flex flex-col gap-0.5" },
            React.createElement("h2", { className: "text-[11px] font-bold tracking-[0.2em] text-accent uppercase flex items-center gap-2" },
              React.createElement("img", { src: "/images/agentellama.png", className: "w-4 h-4 object-contain" }), " LLAMA QUANTUM"
            ),
            isLoading && React.createElement("div", { className: "flex items-center gap-2" },
              React.createElement("span", { className: "flex items-center gap-1.5 text-[8px] bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full border border-red-500/30 animate-pulse font-black" },
                React.createElement("i", { className: "fas fa-robot" }), " AGENT WORKING..."
              ),
              React.createElement("button", {
                onClick: () => {
                  if (abortControllerRef.current) abortControllerRef.current.abort();
                  setIsLoading(false);
                  setIsAiWriting(false);
                },
                className: "text-[8px] text-muted hover:text-red-400 underline uppercase tracking-tighter"
              }, "Cancel Task")
            )
          ),
          React.createElement("button", { onClick: clearChatHistory, title: "Clear Memory", className: "text-muted hover:text-red-400 transition-colors" },
            React.createElement("i", { className: "fas fa-trash-alt text-[10px]" })
          )
        ),
        React.createElement("div", { className: "flex-1 overflow-y-auto p-4 space-y-4 no-scrollbar" },
          chatMessages.length === 0 &&
          React.createElement("div", { className: "flex flex-col items-center justify-center h-full text-center space-y-4 opacity-30 mt-10 shrink-0" },
            React.createElement("img", { src: "/images/agentellama.png", className: "w-16 h-16 object-contain grayscale" }),
            React.createElement("p", { className: "text-[10px] uppercase tracking-[0.2em] leading-relaxed" }, "Hi, I'm ",
              React.createElement("span", { className: "text-accent font-bold" }, "LLAMA QUANTUM"), ".", React.createElement("br", null), "Ask me to create an indicator,", React.createElement("br", null), "a strategy, or use /skill."
            )
          ),
          chatMessages.map((msg, i) =>
            React.createElement("div", { key: i, className: `flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}` },
              React.createElement("div", { className: `max-w-[95%] p-3 rounded-lg text-[11px] leading-relaxed shadow-lg ${msg.role === 'user' ? 'bg-accent/20 text-accent border border-accent/30' : 'bg-white/5 text-text/90 border border-white/10 italic'}` },
                msg.content ? msg.content.split(':::').map((part, idx) => {
                  if (idx % 2 === 1 && part.startsWith('BACKTEST_REPORT')) {
                    // Render Professional Report Card
                    const lines = part.split('\n');
                    const stats = {};
                    lines.forEach(l => {
                      const [k, v] = l.split(':').map(s => s.trim());
                      if (k && v) stats[k] = v;
                    });
                    const isProfitable = parseFloat(stats.total_pnl || 0) >= 0;
                    
                    return React.createElement("div", { key: idx, className: "my-3 bg-black/40 border border-white/10 rounded-xl overflow-hidden shadow-2xl backdrop-blur-md not-italic" },
                      React.createElement("div", { className: `px-4 py-2 border-b border-white/5 flex justify-between items-center ${isProfitable ? 'bg-success/10' : 'bg-red-500/10'}` },
                        React.createElement("span", { className: "text-[10px] font-black tracking-widest text-white flex items-center gap-2 uppercase" }, 
                          React.createElement("i", { className: "fas fa-chart-line" }), `PERFORMANCE REPORT: ${stats.symbol || '---'}`
                        ),
                        React.createElement("div", { className: `text-[10px] font-bold px-2 py-0.5 rounded ${isProfitable ? 'bg-success text-black' : 'bg-red-500 text-white'}` },
                          isProfitable ? 'PROFITABLE' : 'LOSS'
                        )
                      ),
                      React.createElement("div", { className: "p-4 grid grid-cols-2 gap-3" },
                        [
                          { label: 'Win Rate', val: stats.win_rate, icon: 'fa-percentage' },
                          { label: 'Net PnL', val: `$${stats.total_pnl}`, icon: 'fa-dollar-sign', color: isProfitable ? 'text-success' : 'text-red-400' },
                          { label: 'Profit Factor', val: stats.profit_factor, icon: 'fa-scale-balanced' },
                          { label: 'Max Drawdown', val: stats.max_drawdown, icon: 'fa-arrow-trend-down', color: 'text-orange-400' }
                        ].map((s, si) => (
                          React.createElement("div", { key: si, className: "bg-white/5 p-2 rounded border border-white/5 flex flex-col gap-1" },
                            React.createElement("div", { className: "text-[8px] text-muted font-bold uppercase tracking-tighter flex items-center gap-1.5" },
                               React.createElement("i", { className: `fas ${s.icon} opacity-50` }), s.label
                            ),
                            React.createElement("div", { className: `text-[13px] font-mono font-black ${s.color || 'text-white'}` }, s.val)
                          )
                        ))
                      ),
                      React.createElement("div", { className: "px-4 py-2 bg-white/5 text-[9px] text-muted/80 border-t border-white/5 flex items-center gap-2" },
                         React.createElement("i", { className: "fas fa-info-circle" }), "Data sourced from Yahoo Finance API"
                      )
                    );
                  }
                  
                  return part.split('```').map((cpart, cidx) => {
                    if (cidx % 2 === 1) {
                      const lines = cpart.split('\n');
                      const code = lines.slice(1).join('\n');
                      return (
                        React.createElement("div", { key: cidx, className: "my-2 bg-black/60 rounded overflow-hidden border border-white/5 group relative not-italic" },
                          React.createElement("div", { className: "flex justify-between items-center px-3 py-1 bg-white/5 border-b border-white/5" },
                            React.createElement("span", { className: "text-[9px] text-muted font-mono" }, lines[0] || 'code'),
                            React.createElement("button", {
                              onClick: () => applyAiCode(code),
                              className: "text-accent hover:text-white text-[9px] font-bold flex items-center gap-1"
                            },
                              React.createElement("i", { className: "fas fa-plus-circle" }), " APPLY"
                            )
                          ),
                          React.createElement("pre", { className: "p-3 overflow-x-auto text-[10px] font-mono text-success/90" }, code)
                        ));
                    }
                    return React.createElement("p", { key: cidx, className: "whitespace-pre-wrap" }, cpart);
                  });
                }) :
                  React.createElement("div", { className: "flex items-center gap-2 py-1" },
                    React.createElement("i", { className: "fas fa-circle-notch fa-spin text-accent" }),
                    React.createElement("span", { className: "animate-pulse" }, "Typing...")
                  )
              )
            )
          ),
          React.createElement("div", { ref: chatEndRef })
        ),
        React.createElement("div", { className: "p-3 border-t border-border bg-black/20 shrink-0" },
          React.createElement("div", { className: "relative" },
            React.createElement("textarea", {
              className: "w-full bg-black/50 border border-border rounded-lg pl-3 pr-10 py-2.5 text-[11px] text-white focus:outline-none focus:border-accent resize-none h-20 font-sans",
              placeholder: "Ask me anything... (use /skill)",
              value: inputMessage,
              onChange: (e) => setInputMessage(e.target.value),
              onKeyDown: (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }
            }
            ),
            React.createElement("button", {
              onClick: handleEnhancePrompt,
              disabled: isLoading || !inputMessage.trim(),
              className: "absolute right-10 bottom-2 p-1.5 transition-all text-muted hover:text-accent disabled:opacity-30",
              title: "Improve Prompt (AI)"
            },
              React.createElement("i", { className: "fas fa-magic text-[10px]" })
            ),
            React.createElement("button", {
              onClick: isLoading ? () => {
                if (abortControllerRef.current) abortControllerRef.current.abort();
                setIsLoading(false);
                setIsAiWriting(false);
              } : handleSendMessage,
              disabled: !isLoading && !inputMessage.trim(),
              className: `absolute right-2 bottom-2 w-8 h-8 flex items-center justify-center transition-all rounded-lg ${
                isLoading 
                ? 'bg-red-500 text-white shadow-[0_0_15px_rgba(239,68,68,0.5)] animate-pulse' 
                : 'text-accent hover:bg-accent/10 disabled:opacity-30'
              }`,
              title: isLoading ? "Stop AI (Cancel)" : "Send"
            },
              isLoading ? React.createElement("i", { className: "fas fa-stop text-xs" }) : React.createElement("i", { className: "fas fa-paper-plane text-xs" })
            )
          ),
          React.createElement("div", { className: "flex gap-1 mt-2 overflow-x-auto no-scrollbar pb-1" },
            React.createElement("button", {
              onClick: () => {
                const newMode = !agenticMode;
                setAgenticMode(newMode);
                localStorage.setItem('algolab_agentic_mode', JSON.stringify(newMode));
              },
              className: `px-2 py-1 rounded text-[9px] font-bold flex items-center gap-1.5 transition-all shrink-0 ${agenticMode ?
                'bg-purple-500/20 border border-purple-500/40 text-purple-400 hover:bg-purple-500 hover:text-white' :
                'bg-muted/20 border border-muted/40 text-muted hover:bg-muted/30'}`,
              title: agenticMode ? 'Agentic Mode: Enabled (AI writes in real time)' : 'Agentic Mode: Disabled'
            },
              React.createElement("i", { className: "fas fa-robot text-[8px]" }),
              agenticMode ? 'AGENTIC' : 'MANUAL',
              isAiWriting && agenticMode &&
              React.createElement("span", { className: "inline-block w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" })
            ),
            ['fourier', 'neural', 'genetic', 'stats'].map((s) =>
              React.createElement("button", {
                key: s, onClick: () => setInputMessage(`/skill ${s} `),
                className: "px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-[9px] text-muted hover:text-accent hover:border-accent transition-all shrink-0"
              },
                "#",
                s
              )
            )
          )
        ),
        isChatOpen &&
        React.createElement("div", {
          onMouseDown: startChatResizing,
          className: "absolute top-0 -left-1 bottom-0 w-2 cursor-ew-resize hover:bg-accent/30 transition-colors z-[60]"
        }
        )
      ),
      showAiSettings &&
      React.createElement(FloatingModal, {
        isOpen: showAiSettings,
        width: 460,
        zIndex: 120,
        storageKey: "algolab_modal_ai_settings",
        onClose: () => setShowAiSettings(false),
        header:
          React.createElement(React.Fragment, null,
            React.createElement("img", { src: "/images/QuantumLLama.png", className: "w-5 h-5 object-contain" }),
            React.createElement("span", { className: "text-[10px] font-black text-accent uppercase tracking-widest italic" }, "Llama Quantum Settings")
          )
      },
        React.createElement("div", { className: "space-y-4" },
          React.createElement("div", { className: "space-y-2" },
            React.createElement("label", { className: "text-[10px] text-muted font-bold tracking-widest uppercase" }, "Provider"),
            React.createElement("select", {
              className: "w-full bg-black/50 border border-border rounded px-4 py-3 text-sm text-white focus:outline-none focus:border-accent",
              value: aiSettings.provider,
              onChange: (e) => setAiSettings({ ...aiSettings, provider: e.target.value })
            },
              React.createElement("option", { value: "openrouter" }, "OpenRouter (Recomendado)"),
              React.createElement("option", { value: "openai" }, "OpenAI (Directo)")
            )
          ),
          React.createElement("div", { className: "space-y-2" },
            React.createElement("label", { className: "text-[10px] text-muted font-bold tracking-widest uppercase" }, "API KEY"),
            React.createElement("input", {
              type: "password",
              className: "w-full bg-black/50 border border-border rounded px-4 py-3 text-sm text-white focus:outline-none focus:border-accent font-mono",
              placeholder: "sk-...",
              value: aiSettings.apiKey,
              onChange: (e) => setAiSettings({ ...aiSettings, apiKey: e.target.value })
            }
            ),
            React.createElement("p", { className: "text-[9px] text-muted/50 mt-1 italic" }, "Your keys are stored securely on the local server.")
          ),
          React.createElement("div", { className: "space-y-2" },
            React.createElement("label", { className: "text-[10px] text-muted font-bold tracking-widest uppercase flex items-center justify-between" }, "Model",
              isFetchingModels && React.createElement("i", { className: "fas fa-spinner fa-spin text-accent" })
            ),
            availableModels.length > 0 ?
              React.createElement("select", {
                className: "w-full bg-black/50 border border-border rounded px-4 py-3 text-sm text-white focus:outline-none focus:border-accent",
                value: aiSettings.model,
                onChange: (e) => setAiSettings({ ...aiSettings, model: e.target.value })
              },
                React.createElement("option", { value: "" }, "Select a model..."),
                availableModels.map((m) =>
                  React.createElement("option", { key: m.id, value: m.id },
                    m.name, " ", m.pricing?.prompt === "0" && "(GRATIS)"
                  )
                )
              ) :
              React.createElement("input", {
                type: "text",
                className: "w-full bg-black/50 border border-border rounded px-4 py-3 text-sm text-white focus:outline-none focus:border-accent font-mono",
                placeholder: "openai/gpt-3.5-turbo",
                value: aiSettings.model,
                onChange: (e) => setAiSettings({ ...aiSettings, model: e.target.value })
              }
              ),
            React.createElement("p", { className: "text-[9px] text-muted/50 mt-1 italic leading-relaxed" },
              availableModels.length > 0 ?
                "Select from the automatically detected list." :
                "Enter the model ID (e.g., anthropic/claude-3-opus, openai/gpt-4-turbo)."
            )
          )
        ),
        React.createElement("div", { className: "flex gap-3 pt-4 border-t border-border" },
          React.createElement("button", {
            onClick: () => setShowAiSettings(false),
            className: "flex-1 px-4 py-2 border border-border rounded text-muted hover:text-white hover:bg-white/5 transition-all text-[10px] font-bold"
          },
            "CANCEL"),
          React.createElement("button", {
            onClick: saveAiSettings,
            className: "flex-1 px-4 py-2 bg-accent text-black rounded hover:opacity-90 transition-all text-[10px] font-bold uppercase"
          },
            "SAVE CHANGES")
        )
      ),
      showNewFileModal &&
      React.createElement(FloatingModal, {
        isOpen: showNewFileModal,
        width: 420,
        zIndex: 120,
        storageKey: "algolab_modal_new_file",
        onClose: () => setShowNewFileModal(false),
        header:
          React.createElement(React.Fragment, null,
            React.createElement("i", { className: "fas fa-plus-circle text-accent text-sm" }),
            React.createElement("span", { className: "text-[10px] font-black text-accent uppercase tracking-widest italic" }, "New Item")
          )
      },
        React.createElement("div", { className: "space-y-4" },
          React.createElement("div", { className: "space-y-2" },
            React.createElement("label", { className: "text-[10px] text-muted font-bold tracking-widest uppercase" }, "Type"),
            React.createElement("div", { className: "grid grid-cols-2 gap-2" },
              React.createElement("button", {
                onClick: () => setNewFileType('indicator'),
                className: `py-3 rounded border transition-all flex flex-col items-center gap-2 ${newFileType === 'indicator' ? 'bg-accent/20 border-accent text-accent' : 'bg-black/40 border-border text-muted hover:border-muted'}`
              },
                React.createElement("i", { className: "fas fa-chart-line text-lg" }),
                React.createElement("span", { className: "text-[10px] font-bold" }, "Indicator")
              ),
              React.createElement("button", {
                onClick: () => setNewFileType('strategy'),
                className: `py-3 rounded border transition-all flex flex-col items-center gap-2 ${newFileType === 'strategy' ? 'bg-accent/20 border-accent text-accent' : 'bg-black/40 border-border text-muted hover:border-muted'}`
              },
                React.createElement("i", { className: "fas fa-brain text-lg" }),
                React.createElement("span", { className: "text-[10px] font-bold" }, "Strategy")
              )
            )
          ),
          React.createElement("div", { className: "space-y-2" },
            React.createElement("label", { className: "text-[10px] text-muted font-bold tracking-widest uppercase" }, "Name"),
            React.createElement("input", {
              type: "text", className: "w-full bg-black/50 border border-border rounded px-4 py-3 text-sm text-white focus:outline-none focus:border-accent font-mono",
              placeholder: "mi_nuevo_script", value: newFileName, onChange: (e) => setNewFileName(e.target.value), autoFocus: true
            }
            ),
            React.createElement("p", { className: "text-[9px] text-muted/50 mt-1" }, "The file will be saved with a .py extension automatically.")
          )
        ),
        React.createElement("div", { className: "flex gap-3 pt-4 border-t border-border" },
          React.createElement("button", {
            onClick: () => setShowNewFileModal(false),
            className: "flex-1 px-4 py-2 border border-border rounded text-muted hover:text-white hover:bg-white/5 transition-all text-[10px] font-bold"
          },
            "CANCEL"),
          React.createElement("button", {
            onClick: handleCreateFile,
            className: "flex-1 px-4 py-2 bg-accent text-black rounded hover:opacity-90 transition-all text-[10px] font-bold uppercase"
          },
            "CREATE FILE")
        )
      ),
      showClearConfirm &&
      React.createElement(FloatingModal, {
        isOpen: showClearConfirm,
        width: 360,
        zIndex: 125,
        storageKey: "algolab_modal_clear_chat",
        onClose: () => setShowClearConfirm(false),
        header:
          React.createElement(React.Fragment, null,
            React.createElement("i", { className: "fas fa-exclamation-triangle text-red-400 text-sm" }),
            React.createElement("span", { className: "text-[10px] font-black text-red-400 uppercase tracking-widest" }, "Clear Memory")
          )
      },
        React.createElement("div", { className: "flex flex-col items-center text-center space-y-4" },
          React.createElement("div", { className: "w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center text-red-500 animate-pulse" },
            React.createElement("i", { className: "fas fa-exclamation-triangle text-xl" })
          ),
          React.createElement("div", { className: "space-y-1" },
            React.createElement("h2", { className: "text-sm font-bold text-white uppercase tracking-widest" }, "Clear Memory?"),
            React.createElement("p", { className: "text-[10px] text-muted leading-relaxed" }, "This action will permanently delete the entire LLAMA QUANTUM conversation history.")
          )
        ),
        React.createElement("div", { className: "flex gap-3 pt-4" },
          React.createElement("button", {
            onClick: () => setShowClearConfirm(false),
            className: "flex-1 px-4 py-2 border border-border rounded text-muted hover:text-white hover:bg-white/5 transition-all text-[10px] font-bold"
          },
            "CANCEL"),
          React.createElement("button", {
            onClick: handleConfirmClearChat,
            className: "flex-1 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-500 transition-all text-[10px] font-bold uppercase"
          },
            "CONFIRM")
        )
      ),
      contextMenu.visible &&
      React.createElement("div", {
        className: "fixed z-[200] bg-panel border border-border shadow-2xl rounded-md py-1 min-w-[140px] animate-in zoom-in-95 duration-100",
        style: { top: contextMenu.y, left: contextMenu.x }
      },
        React.createElement("button", {
          onClick: () => { setRenameName(contextMenu.file.name.replace('.py', '')); setShowRenameModal(true); },
          className: "w-full text-left px-4 py-2 text-xs text-text/80 hover:bg-accent hover:text-black transition-all flex items-center gap-2"
        },
          React.createElement("i", { className: "fas fa-edit opacity-70" }), " Rename"
        ),
        React.createElement("button", {
          onClick: () => setFileToDelete(contextMenu.file),
          className: "w-full text-left px-4 py-2 text-xs text-red-400 hover:bg-red-500 hover:text-white transition-all flex items-center gap-2"
        },
          React.createElement("i", { className: "fas fa-trash-alt opacity-70" }), " Delete"
        )
      ),
      showRenameModal &&
      React.createElement(FloatingModal, {
        isOpen: showRenameModal,
        width: 360,
        zIndex: 130,
        storageKey: "algolab_modal_rename_file",
        onClose: () => setShowRenameModal(false),
        header:
          React.createElement(React.Fragment, null,
            React.createElement("i", { className: "fas fa-edit text-accent text-sm" }),
            React.createElement("span", { className: "text-[10px] font-black text-accent uppercase tracking-widest italic" }, "Rename File")
          )
      },
        React.createElement("input", {
          type: "text", className: "w-full bg-black/50 border border-border rounded px-4 py-3 text-sm text-white focus:outline-none focus:border-accent font-mono",
          value: renameName, onChange: (e) => setRenameName(e.target.value), autoFocus: true,
          onKeyDown: (e) => e.key === 'Enter' && handleRenameFile()
        }
        ),
        React.createElement("div", { className: "flex gap-3 pt-4" },
          React.createElement("button", {
            onClick: () => setShowRenameModal(false),
            className: "flex-1 px-4 py-2 border border-border rounded text-muted hover:text-white hover:bg-white/5 transition-all text-[10px] font-bold"
          },
            "CANCEL"),
          React.createElement("button", {
            onClick: handleRenameFile,
            className: "flex-1 px-4 py-2 bg-accent text-black rounded hover:opacity-90 transition-all text-[10px] font-bold uppercase"
          },
            "SAVE")
        )
      ),
      fileToDelete &&
      React.createElement(FloatingModal, {
        isOpen: Boolean(fileToDelete),
        width: 360,
        zIndex: 130,
        storageKey: "algolab_modal_delete_file",
        onClose: () => setFileToDelete(null),
        header:
          React.createElement(React.Fragment, null,
            React.createElement("i", { className: "fas fa-trash-alt text-red-400 text-sm" }),
            React.createElement("span", { className: "text-[10px] font-black text-red-400 uppercase tracking-widest" }, "Delete File")
          )
      },
        React.createElement("div", { className: "flex flex-col items-center text-center space-y-4" },
          React.createElement("div", { className: "w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center text-red-500" },
            React.createElement("i", { className: "fas fa-trash-alt text-xl" })
          ),
          React.createElement("div", { className: "space-y-1" },
            React.createElement("h2", { className: "text-sm font-bold text-white uppercase tracking-widest" }, "Delete File?"),
            React.createElement("p", { className: "text-[10px] text-muted leading-relaxed" }, "You are about to delete ",
              React.createElement("span", { className: "text-white font-bold" }, fileToDelete.name), ". This action is irreversible and could affect linked strategies."
            )
          )
        ),
        React.createElement("div", { className: "flex gap-3 pt-4" },
          React.createElement("button", {
            onClick: () => setFileToDelete(null),
            className: "flex-1 px-4 py-2 border border-border rounded text-muted hover:text-white hover:bg-white/5 transition-all text-[10px] font-bold"
          },
            "CANCEL"),
          React.createElement("button", {
            onClick: handleDeleteFile,
            className: "flex-1 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-500 transition-all text-[10px] font-bold uppercase"
          },
            "DELETE")
        )
      ),
      showDependencyModal &&
      React.createElement(FloatingModal, {
        isOpen: showDependencyModal,
        width: 420,
        zIndex: 135,
        storageKey: "algolab_modal_dependencies",
        onClose: () => setShowDependencyModal(false),
        header:
          React.createElement(React.Fragment, null,
            React.createElement("i", { className: "fas fa-wrench text-yellow-400 text-sm" }),
            React.createElement("span", { className: "text-[10px] font-black text-yellow-400 uppercase tracking-widest italic" }, "Missing Libraries")
          )
      },
        React.createElement("div", { className: "bg-black/40 rounded p-4 border border-white/5" },
          React.createElement("p", { className: "text-[11px] text-muted mb-3" }, "The following missing libraries were detected in your code:"),
          React.createElement("ul", { className: "space-y-1" },
            missingDependencies.map((dep, idx) =>
              React.createElement("li", { key: idx, className: "text-xs font-mono text-accent flex items-center gap-2" },
                React.createElement("i", { className: "fas fa-box-open text-[10px]" }), " ", dep
              )
            )
          )
        ),
        React.createElement("div", { className: "flex gap-3 pt-4" },
          React.createElement("button", {
            onClick: () => setShowDependencyModal(false),
            className: "flex-1 px-4 py-2 border border-border rounded text-muted hover:text-white hover:bg-white/5 transition-all text-[10px] font-bold"
          },
            "CANCEL"),
          React.createElement("button", {
            onClick: handleInstallDependencies, disabled: isInstallingDeps,
            className: "flex-1 px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-500 transition-all text-[10px] font-bold uppercase flex items-center justify-center gap-2"
          },
            isInstallingDeps ? React.createElement("i", { className: "fas fa-spinner fa-spin" }) : React.createElement("i", { className: "fas fa-download" }),
            isInstallingDeps ? 'INSTALLING...' : 'INSTALL NOW'
          )
        )
      )
    ));
};
window.AlgoLab = AlgoLab;