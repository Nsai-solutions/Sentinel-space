import { useState, useEffect, useRef } from 'react';
import { getNotificationPrefs, updateNotificationPrefs } from '../../api/client';
import toast from 'react-hot-toast';
import './NotificationSettings.css';

export default function NotificationSettings({ onClose, embedded }) {
  const [prefs, setPrefs] = useState(null);
  const [saving, setSaving] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    getNotificationPrefs()
      .then((res) => setPrefs(res.data))
      .catch(console.error);
  }, []);

  // Close on click outside (only for standalone dropdown mode)
  useEffect(() => {
    if (embedded) return;
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose, embedded]);

  const handleSave = async (updated) => {
    setPrefs(updated);
    setSaving(true);
    try {
      await updateNotificationPrefs(updated);
      toast.success('Settings saved');
    } catch {
      toast.error('Failed to save');
    }
    setSaving(false);
  };

  if (!prefs) {
    return (
      <div className={embedded ? 'notif-embedded' : 'notif-dropdown'} ref={ref}>
        <div className="notif-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className={embedded ? 'notif-embedded' : 'notif-dropdown'} ref={ref}>
      {!embedded && (
        <div className="notif-header">
          <span>Email Notifications</span>
          <button className="notif-close" onClick={onClose}>&times;</button>
        </div>
      )}

      <label className="notif-row">
        <span className="notif-label">Email</span>
        <input
          type="email"
          className="notif-input"
          value={prefs.email || ''}
          placeholder="your@email.com"
          onChange={(e) => handleSave({ ...prefs, email: e.target.value })}
        />
      </label>

      <label className="notif-row">
        <span className="notif-label">Enabled</span>
        <input
          type="checkbox"
          checked={prefs.email_enabled}
          onChange={(e) => handleSave({ ...prefs, email_enabled: e.target.checked })}
        />
      </label>

      <div className="notif-levels-header">Notify on:</div>
      <div className="notif-levels">
        {[
          { key: 'notify_critical', label: 'CRITICAL', cls: 'critical' },
          { key: 'notify_high', label: 'HIGH', cls: 'high' },
          { key: 'notify_moderate', label: 'MODERATE', cls: 'moderate' },
          { key: 'notify_low', label: 'LOW', cls: 'low' },
        ].map(({ key, label, cls }) => (
          <label key={key} className="notif-level-row">
            <input
              type="checkbox"
              checked={prefs[key]}
              onChange={(e) => handleSave({ ...prefs, [key]: e.target.checked })}
            />
            <span className={`notif-level-badge ${cls}`}>{label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
