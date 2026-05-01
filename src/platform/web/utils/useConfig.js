import { useState, useEffect } from 'react';
import configDB from './config_db.js';
export function useConfig(key, defaultValue = null, category = 'general') {
  const [value, setValue] = useState(() => {
    return configDB.getSync(key, defaultValue);
  });
  const [isLoading, setIsLoading] = useState(true);
  useEffect(() => {
    configDB.get(key, defaultValue).then((dbValue) => {
      setValue(dbValue);
      setIsLoading(false);
    });
  }, [key, defaultValue]);
  const updateValue = async (newValue) => {
    setValue(newValue);
    await configDB.set(key, newValue, category);
  };
  return [value, updateValue, isLoading];
}
export function useConfigs(configs) {
  const [values, setValues] = useState(() => {
    const initial = {};
    configs.forEach(({ key, defaultValue }) => {
      initial[key] = configDB.getSync(key, defaultValue);
    });
    return initial;
  });
  const [isLoading, setIsLoading] = useState(true);
  useEffect(() => {
    Promise.all(
      configs.map(({ key, defaultValue }) =>
      configDB.get(key, defaultValue).then((value) => ({ key, value }))
      )
    ).then((results) => {
      const newValues = {};
      results.forEach(({ key, value }) => {
        newValues[key] = value;
      });
      setValues(newValues);
      setIsLoading(false);
    });
  }, [JSON.stringify(configs.map((c) => c.key))]);
  const setters = {};
  configs.forEach(({ key, category = 'general' }) => {
    setters[key] = async (newValue) => {
      setValues((prev) => ({ ...prev, [key]: newValue }));
      await configDB.set(key, newValue, category);
    };
  });
  return [values, setters, isLoading];
}
export function useMigrateLocalStorage() {
  const [migrated, setMigrated] = useState(false);
  useEffect(() => {
    const migrate = async () => {
      const alreadyMigrated = await configDB.get('_migration_completed', false);
      if (!alreadyMigrated) {
        await configDB.migrateFromLocalStorage();
        await configDB.set('_migration_completed', true, 'system');
        setMigrated(true);
      } else {
        setMigrated(true);
      }
    };
    migrate();
  }, []);
  return migrated;
}
export default useConfig;