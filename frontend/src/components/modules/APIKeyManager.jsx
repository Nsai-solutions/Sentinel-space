import { useState, useEffect } from 'react';
import { listAPIKeys, createAPIKey, revokeAPIKey } from '../../api/client';
import toast from 'react-hot-toast';
import './APIKeyManager.css';

export default function APIKeyManager() {
  const [keys, setKeys] = useState([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadKeys();
  }, []);

  const loadKeys = async () => {
    try {
      const res = await listAPIKeys();
      setKeys(res.data);
    } catch (err) {
      console.error('Failed to load API keys:', err);
    }
  };

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setCreating(true);
    try {
      const res = await createAPIKey({ name: newKeyName });
      setCreatedKey(res.data.key);
      setNewKeyName('');
      loadKeys();
      toast.success('API key created');
    } catch (err) {
      toast.error('Failed to create API key');
    }
    setCreating(false);
  };

  const handleRevoke = async (id, name) => {
    try {
      await revokeAPIKey(id);
      loadKeys();
      toast.success(`Key "${name}" revoked`);
    } catch (err) {
      toast.error('Failed to revoke key');
    }
  };

  const handleCopy = () => {
    if (createdKey) {
      navigator.clipboard.writeText(createdKey);
      toast.success('Copied to clipboard');
    }
  };

  return (
    <div className="api-key-manager">
      <div className="section-title">API KEYS</div>

      {createdKey && (
        <div className="key-created-banner">
          <p className="key-created-warning">Copy your key now. It won't be shown again.</p>
          <div className="key-created-value">
            <code className="font-data">{createdKey}</code>
            <button className="btn-copy" onClick={handleCopy}>Copy</button>
          </div>
          <button className="btn-dismiss" onClick={() => setCreatedKey(null)}>Dismiss</button>
        </div>
      )}

      <div className="key-create-form">
        <input
          type="text"
          className="key-name-input"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          placeholder="Key name (e.g., Production)"
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
        />
        <button
          className="btn-primary btn-create-key"
          onClick={handleCreate}
          disabled={creating || !newKeyName.trim()}
        >
          Create
        </button>
      </div>

      {keys.length > 0 && (
        <div className="key-list">
          {keys.map((k) => (
            <div key={k.id} className={`key-row ${!k.is_active ? 'revoked' : ''}`}>
              <div className="key-info">
                <span className="key-name">{k.name}</span>
                <code className="key-prefix font-data">{k.key_prefix}...</code>
              </div>
              <div className="key-actions">
                {k.is_active ? (
                  <button
                    className="btn-revoke"
                    onClick={() => handleRevoke(k.id, k.name)}
                  >
                    Revoke
                  </button>
                ) : (
                  <span className="revoked-label">Revoked</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
