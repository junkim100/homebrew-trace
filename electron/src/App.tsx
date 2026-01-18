import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Permissions from './pages/permissions';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/permissions" element={<Permissions />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
