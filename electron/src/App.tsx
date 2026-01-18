import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Chat from './pages/Chat';
import Settings from './pages/Settings';
import Permissions from './pages/permissions';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/permissions" element={<Permissions />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
