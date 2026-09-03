import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Activity, RefreshCcw, ShieldAlert, Cpu, BarChart3, AlertCircle } from 'lucide-react';
import { simulateScenario } from './api/client';
import razorpayLogo from './assets/razorpay_logo.svg';
import rallyLogo from './assets/rally_logo.png';

import Overview from './pages/Overview';
import Feed from './pages/Feed';
import DecisionExplorer from './pages/DecisionExplorer';
import Lifecycle from './pages/Lifecycle';
import Safety from './pages/Safety';
import Evaluation from './pages/Evaluation';
import Architecture from './pages/Architecture';

function Sidebar() {
  const location = useLocation();
  const navItems = [
    { path: '/', label: 'Overview', icon: <LayoutDashboard size={17} /> },
    { path: '/feed', label: 'Live Decision Feed', icon: <Activity size={17} /> },
    { path: '/lifecycle', label: 'Payment Lifecycle', icon: <RefreshCcw size={17} /> },
    { path: '/safety', label: 'Safety & Failures', icon: <ShieldAlert size={17} /> },
    { path: '/evaluation', label: 'Evaluation', icon: <BarChart3 size={17} /> },
    { path: '/architecture', label: 'Architecture', icon: <Cpu size={17} /> },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-section-header">OPERATIONS</div>
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </Link>
        ))}
      </nav>
    </aside>
  );
}

function SimulationControls() {
  const handleSimulate = async (scenario) => {
    try {
      await simulateScenario(scenario);
      window.dispatchEvent(new Event('simulationUpdate'));
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="sim-controls">
      <div className="scientific-boundary">
        <AlertCircle size={15} />
        <span>Simulation Mode — Synthetic Events</span>
      </div>
      <div className="sim-actions">
        <button className="btn" onClick={() => handleSimulate('normal')}>Generate Failure</button>
        <button className="btn" onClick={() => handleSimulate('timeout')}>Trigger Timeout</button>
        <button className="btn" onClick={() => handleSimulate('late_capture')}>Trigger Late Capture</button>
        <button className="btn" onClick={() => handleSimulate('stale_features')}>Trigger Stale Features</button>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-container">
        
        {/* Top Navigation Bar */}
        <header className="top-bar">
          <div className="top-bar-left">
            <div className="brand-group">
              <div className="brand-title-row" aria-label="Rally">
                <img src={rallyLogo} alt="R" className="brand-logo-r" />
                <span className="brand-title">ALLY</span>
              </div>
              <span className="brand-descriptor">Safe AI Revenue Recovery Decisioning</span>
            </div>
          </div>

          <div className="top-bar-center">
            <div className="header-status-pill">
              <span className="status-indicator-dot"></span>
              <span className="status-engine-text">Causal Recovery Engine</span>
              <span className="status-separator">|</span>
              <span className="status-badge-text">ACTIVE</span>
            </div>
          </div>

          <div className="top-bar-right">
            <div className="buildathon-badge">
              <span>BUILT FOR</span>
              <img src={razorpayLogo} alt="Razorpay" className="buildathon-logo" />
              <span>BUILDATHON</span>
            </div>
          </div>
        </header>

        {/* Dashboard Canvas with Curved Transitions */}
        <div className="main-shell">
          <div className="header-tab">
            <span className="tab-dot"></span>
            <span>SIMULATION CONSOLE</span>
          </div>

          <div className="main-body">
            <Sidebar />
            <main className="main-content">
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/feed" element={<Feed />} />
                <Route path="/decision/:id" element={<DecisionExplorer />} />
                <Route path="/lifecycle" element={<Lifecycle />} />
                <Route path="/safety" element={<Safety />} />
                <Route path="/evaluation" element={<Evaluation />} />
                <Route path="/architecture" element={<Architecture />} />
              </Routes>
            </main>
          </div>
        </div>

        <SimulationControls />
      </div>
    </BrowserRouter>
  );
}
