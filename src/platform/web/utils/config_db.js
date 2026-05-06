const DB_NAME = 'QuantumLlamaConfig';
const DB_VERSION = 1;
const STORE_NAME = 'settings';
class ConfigDB {
  constructor() {
    this.db = null;
    this.cache = new Map();
    this.isElectron = typeof window !== 'undefined' && (
    window.electronAPI && window.electronAPI.isElectron ||
    navigator.userAgent.toLowerCase().indexOf(' electron/') > -1);
    
    if (this.isElectron && (!window.electronAPI || !window.electronAPI.configLoad)) {
      console.warn('[ConfigDB] Electron detected but bridge API missing. Persistence may fail.');
    }
    this.initPromise = this.init();
  }
  async init() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onerror = () => {
        console.error('[ConfigDB] IndexedDB error:', request.error);
        reject(request.error);
      };
      request.onsuccess = async () => {
        this.db = request.result;
        try {
          await this.loadCache();
          if (this.isElectron) {
            await this.ensureElectronConnection();
            await this.syncFromElectron();
          }
          resolve();
        } catch (e) {
          console.error('[ConfigDB] Init sync error:', e);
          resolve();
        }
      };
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'key' });
          store.createIndex('category', 'category', { unique: false });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };
    });
  }
  async ensureElectronConnection(retries = 5) {
    if (window.electronAPI) return true;
    `);
    for (let i = 0; i < retries; i++) {
      await new Promise((r) => setTimeout(r, 500));
      if (window.electronAPI) {
        
        return true;
      }
    }
    console.error('[ConfigDB] Electron Bridge failed to connect.');
    return false;
  }
  async syncFromElectron() {
    if (!this.isElectron || !window.electronAPI) return;
    try {
      
      if (window.electronAPI.test) {
        try {await window.electronAPI.test();}
        catch (e) {console.warn('[ConfigDB] Bridge test failed:', e);}
      }
      const raw = await window.electronAPI.configLoad();
      if (raw) {
        const data = JSON.parse(raw);
        if (Array.isArray(data)) {
          await this.import(data);
          
        } else if (typeof data === 'object') {
          const items = Object.entries(data).map(([key, value]) => ({
            key,
            value,
            category: 'general',
            timestamp: Date.now()
          }));
          await this.import(items);
          
        }
      } else {
        
      }
    } catch (e) {
      console.error('[ConfigDB] syncFromElectron error:', e);
    }
  }
  async syncToElectron() {
    if (!this.isElectron) return;
    if (!window.electronAPI) {
      console.warn('[ConfigDB] syncToElectron: API missing, retrying connection...');
      await this.ensureElectronConnection(3);
      if (!window.electronAPI) {
        console.error('[ConfigDB] syncToElectron failed: No API');
        return;
      }
    }
    try {
      const allData = await this.export();
      const raw = JSON.stringify(allData);
      await window.electronAPI.configSave(raw);
      
    } catch (e) {
      console.error('[ConfigDB] syncToElectron error:', e);
    }
  }
  async loadCache() {
    return new Promise((resolve, reject) => {
      if (!this.db) {
        resolve();
        return;
      }
      const transaction = this.db.transaction([STORE_NAME], 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.getAll();
      request.onsuccess = () => {
        request.result.forEach((item) => {
          this.cache.set(item.key, item.value);
        });
        resolve();
      };
      request.onerror = () => reject(request.error);
    });
  }
  async get(key, defaultValue = null) {
    if (this.cache.has(key)) {
      return this.cache.get(key);
    }
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([STORE_NAME], 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.get(key);
      request.onsuccess = () => {
        const value = request.result ? request.result.value : defaultValue;
        this.cache.set(key, value);
        resolve(value);
      };
      request.onerror = () => {
        console.warn(`ConfigDB: Error getting ${key}, using default`, request.error);
        resolve(defaultValue);
      };
    });
  }
  getSync(key, defaultValue = null) {
    return this.cache.has(key) ? this.cache.get(key) : defaultValue;
  }
  async set(key, value, category = 'general') {
    await this.initPromise;
    this.cache.set(key, value);
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.put({
        key,
        value,
        category,
        timestamp: Date.now()
      });
      request.onsuccess = async () => {
        if (this.isElectron) {
          this.syncToElectron().catch(console.error);
        }
        resolve();
      };
      request.onerror = () => {
        console.error(`ConfigDB: Error setting ${key}`, request.error);
        reject(request.error);
      };
    });
  }
  async delete(key) {
    await this.initPromise;
    this.cache.delete(key);
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.delete(key);
      request.onsuccess = async () => {
        if (this.isElectron) {
          this.syncToElectron().catch(console.error);
        }
        resolve();
      };
      request.onerror = () => reject(request.error);
    });
  }
  async getByCategory(category) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([STORE_NAME], 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const index = store.index('category');
      const request = index.getAll(category);
      request.onsuccess = () => {
        const results = {};
        request.result.forEach((item) => {
          results[item.key] = item.value;
        });
        resolve(results);
      };
      request.onerror = () => reject(request.error);
    });
  }
  async clear() {
    await this.initPromise;
    this.cache.clear();
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.clear();
      request.onsuccess = async () => {
        if (this.isElectron) {
          this.syncToElectron().catch(console.error);
        }
        resolve();
      };
      request.onerror = () => reject(request.error);
    });
  }
  async migrateFromLocalStorage() {
    const keysToMigrate = [
    { key: 'chart_show_volume', category: 'visibility' },
    { key: 'chart_show_delta', category: 'visibility' },
    { key: 'chart_show_grid', category: 'visibility' },
    { key: 'show_all_overlays', category: 'visibility' },
    { key: 'chart_volume_color', category: 'colors' },
    { key: 'chart_delta_color', category: 'colors' },
    { key: 'user_drawings_v2', category: 'drawings' },
    { key: 'saved_workspaces', category: 'workspaces' },
    { key: 'cazastop_settings', category: 'indicators' },
    { key: 'overlay_settings', category: 'indicators' }];
    let migratedAny = false;
    for (const { key, category } of keysToMigrate) {
      const value = localStorage.getItem(key);
      if (value !== null) {
        try {
          const parsed = JSON.parse(value);
          await this.set(key, parsed, category);
          migratedAny = true;
        } catch (e) {
          await this.set(key, value, category);
          migratedAny = true;
        }
      }
    }
    if (migratedAny && this.isElectron) {
      await this.syncToElectron();
    }
  }
  async export() {
    return new Promise((resolve, reject) => {
      if (!this.db) return resolve([]);
      const transaction = this.db.transaction([STORE_NAME], 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  async import(data) {
    return new Promise((resolve, reject) => {
      if (!this.db) return reject(new Error('DB not initialized'));
      const transaction = this.db.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      for (const item of data) {
        store.put(item);
        this.cache.set(item.key, item.value);
      }
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  }
}
const configDB = new ConfigDB();
export default configDB;
if (typeof window !== 'undefined') {
  window.configDB = configDB;
}
