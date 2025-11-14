import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { v4 } from 'uuid';

export interface SessionInfo {
  sessionId: string;
  userId?: string;
  customerName?: string;
  tabId?: string;
  createdAt: Date;
  lastUsed: Date;
  messageCount?: number;
  title?: string;
}

interface StoredTabSessions {
  sessions: SessionInfo[];
  activeSessionId: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class SessionManagerService {
  private currentSession: SessionInfo | null = null;
  private sessionSubject = new BehaviorSubject<SessionInfo | null>(null);
  private readonly STORAGE_KEY_PREFIX = 'tab-sessions';
  private readonly SESSION_EXPIRY_HOURS = 24;

  public session$: Observable<SessionInfo | null> = this.sessionSubject.asObservable();

  constructor() { }

  /**
   * Initialize or update the current session with user information
   */
  initializeSession(userId?: string | null, customerName?: string | null, tabId?: string): SessionInfo {
    const normalizedUserId = userId || undefined;
    const normalizedCustomerName = customerName || undefined;

    // Load stored sessions for this tab
    const storageKey = this.getStorageKey(normalizedUserId, normalizedCustomerName, tabId);
    const storedData = this.loadStoredSessions(storageKey);

    // Check if we have an active session
    if (storedData.activeSessionId) {
      const activeSession = storedData.sessions.find(s => s.sessionId === storedData.activeSessionId);
      if (activeSession && !this.isSessionExpired(activeSession)) {
        activeSession.lastUsed = new Date();
        this.currentSession = activeSession;
        this.saveStoredSessions(storageKey, storedData);
        this.sessionSubject.next(this.currentSession);
        return this.currentSession;
      }
    }

    // Create new session
    const newSession = this.createNewSessionInternal(normalizedUserId, normalizedCustomerName, tabId);
    storedData.sessions.push(newSession);
    storedData.activeSessionId = newSession.sessionId;
    this.saveStoredSessions(storageKey, storedData);

    this.currentSession = newSession;
    this.sessionSubject.next(this.currentSession);
    return newSession;
  }

  /**
   * Get all sessions for a specific tab
   */
  getTabSessions(userId?: string, customerName?: string, tabId?: string): SessionInfo[] {
    const storageKey = this.getStorageKey(userId, customerName, tabId);
    const storedData = this.loadStoredSessions(storageKey);

    // Filter out expired sessions
    const validSessions = storedData.sessions.filter(s => !this.isSessionExpired(s));

    // Update storage if we filtered out any sessions
    if (validSessions.length !== storedData.sessions.length) {
      storedData.sessions = validSessions;
      this.saveStoredSessions(storageKey, storedData);
    }

    // Sort by last used (most recent first)
    return validSessions.sort((a, b) =>
      new Date(b.lastUsed).getTime() - new Date(a.lastUsed).getTime()
    );
  }

  /**
   * Create a new session for a tab
   */
  createNewSession(userId?: string, customerName?: string, tabId?: string): SessionInfo {
    const storageKey = this.getStorageKey(userId, customerName, tabId);
    const storedData = this.loadStoredSessions(storageKey);

    const newSession = this.createNewSessionInternal(userId, customerName, tabId);
    storedData.sessions.push(newSession);
    storedData.activeSessionId = newSession.sessionId;
    this.saveStoredSessions(storageKey, storedData);

    this.currentSession = newSession;
    this.sessionSubject.next(this.currentSession);
    return newSession;
  }

  /**
   * Switch to a different session
   */
  switchSession(sessionId: string, userId?: string, customerName?: string, tabId?: string): SessionInfo | null {
    const storageKey = this.getStorageKey(userId, customerName, tabId);
    const storedData = this.loadStoredSessions(storageKey);

    const session = storedData.sessions.find(s => s.sessionId === sessionId);
    if (session && !this.isSessionExpired(session)) {
      session.lastUsed = new Date();
      storedData.activeSessionId = sessionId;
      this.saveStoredSessions(storageKey, storedData);
      this.currentSession = session;
      this.sessionSubject.next(this.currentSession);
      return session;
    }

    return null;
  }

  /**
   * Update session message count
   */
  updateSessionMessageCount(sessionId: string, userId?: string, customerName?: string, tabId?: string): void {
    const storageKey = this.getStorageKey(userId, customerName, tabId);
    const storedData = this.loadStoredSessions(storageKey);

    const session = storedData.sessions.find(s => s.sessionId === sessionId);
    if (session) {
      session.messageCount = (session.messageCount || 0) + 1;
      session.lastUsed = new Date();
      this.saveStoredSessions(storageKey, storedData);
    }
  }

  /**
   * Delete a session
   */
  deleteSession(sessionId: string, userId?: string, customerName?: string, tabId?: string): void {
    const storageKey = this.getStorageKey(userId, customerName, tabId);
    const storedData = this.loadStoredSessions(storageKey);

    storedData.sessions = storedData.sessions.filter(s => s.sessionId !== sessionId);

    if (storedData.activeSessionId === sessionId) {
      storedData.activeSessionId = null;
    }

    this.saveStoredSessions(storageKey, storedData);

    if (this.currentSession?.sessionId === sessionId) {
      this.currentSession = null;
      this.sessionSubject.next(null);
    }
  }

  getCurrentSession(userId?: string | null, customerName?: string | null, tabId?: string): SessionInfo {
    // Generate or retrieve tab-specific ID from sessionStorage
    if (!tabId) {
      tabId = sessionStorage.getItem('browserTabId') || undefined;
      if (!tabId) {
        tabId = `tab-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        sessionStorage.setItem('browserTabId', tabId);
      }
    }

    if (!this.currentSession) {
      return this.initializeSession(userId, customerName, tabId);
    }
    this.currentSession.lastUsed = new Date();
    return this.currentSession;
  }

  getCurrentSessionId(userId?: string | null, customerName?: string | null, tabId?: string): string {
    return this.getCurrentSession(userId, customerName, tabId).sessionId;
  }

  clearSession(): void {
    this.currentSession = null;
    this.sessionSubject.next(null);
  }

  updateCustomer(customerName?: string | null, tabId?: string): SessionInfo {
    const userId = this.currentSession?.userId;
    this.clearSession();
    return this.initializeSession(userId, customerName, tabId);
  }

  isSessionValid(): boolean {
    if (!this.currentSession) return false;
    return !this.isSessionExpired(this.currentSession);
  }

  getSessionInfo(): SessionInfo | null {
    return this.currentSession;
  }

  private createNewSessionInternal(userId?: string, customerName?: string, tabId?: string): SessionInfo {
    const sessionId = this.generateSessionId(userId, customerName, tabId);
    return {
      sessionId,
      userId,
      customerName,
      tabId,
      createdAt: new Date(),
      lastUsed: new Date(),
      messageCount: 0,
      title: this.generateSessionTitle(new Date())
    };
  }

  private generateSessionId(userId?: string | null, customerName?: string | null, tabId?: string): string {
    const baseId = v4();
    const sanitizedUserId = userId ? userId.replace(/[^a-zA-Z0-9]/g, '-') : 'anonymous';
    const sanitizedCustomerName = customerName ? customerName.replace(/[^a-zA-Z0-9]/g, '-') : `demo-${Date.now()}`;
    const tabPart = tabId ? `-${tabId}` : '';
    return `${sanitizedUserId}-${sanitizedCustomerName}${tabPart}-${baseId}`;
  }

  private generateSessionTitle(date: Date): string {
    const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const timeStr = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    return `${dateStr} at ${timeStr}`;
  }

  private getStorageKey(userId?: string, customerName?: string, tabId?: string): string {
    const userPart = userId || 'anonymous';
    const customerPart = customerName ? `-${customerName}` : '';
    const tabPart = tabId ? `-${tabId}` : '';
    return `${this.STORAGE_KEY_PREFIX}-${userPart}${customerPart}${tabPart}`;
  }

  private isSessionExpired(session: SessionInfo): boolean {
    const now = new Date().getTime();
    const lastUsed = new Date(session.lastUsed).getTime();
    const hoursSinceActivity = (now - lastUsed) / (1000 * 60 * 60);
    return hoursSinceActivity > this.SESSION_EXPIRY_HOURS;
  }

  private loadStoredSessions(storageKey: string): StoredTabSessions {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        parsed.sessions = parsed.sessions.map((s: any) => ({
          ...s,
          createdAt: new Date(s.createdAt),
          lastUsed: new Date(s.lastUsed)
        }));
        return parsed;
      }
    } catch (error) {
      console.warn('Failed to load sessions from localStorage:', error);
    }
    return { sessions: [], activeSessionId: null };
  }

  private saveStoredSessions(storageKey: string, data: StoredTabSessions): void {
    try {
      localStorage.setItem(storageKey, JSON.stringify(data));
    } catch (error) {
      console.error('Failed to save sessions to localStorage:', error);
    }
  }
}
