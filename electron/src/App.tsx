import { HashRouter, Routes, Route } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import Home from './pages/Home';
import Chat from './pages/Chat';
import Settings from './pages/Settings';
import Permissions from './pages/permissions';
import Graph from './pages/Graph';
import Dashboard from './pages/Dashboard';

function App() {
  return (
    <ErrorBoundary>
      <HashRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/permissions" element={<Permissions />} />
          <Route path="/graph" element={<Graph />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </HashRouter>
    </ErrorBoundary>
  );
}

export default App;
