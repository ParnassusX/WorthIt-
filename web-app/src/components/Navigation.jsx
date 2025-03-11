import { useState } from 'react';
import './Navigation.css';

function Navigation({ onNavigate }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const handleMenuToggle = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  const handleNavigation = (page) => {
    onNavigate(page);
    setIsMenuOpen(false);
  };

  return (
    <nav className="navigation">
      <div className="nav-brand">WorthIt!</div>
      
      <div className="nav-menu-toggle" onClick={handleMenuToggle}>
        <span className="menu-icon">☰</span>
      </div>
      
      <div className={`nav-menu ${isMenuOpen ? 'open' : ''}`}>
        <ul className="nav-links">
          <li onClick={() => handleNavigation('home')}>Home</li>
          <li onClick={() => handleNavigation('profile')}>My Profile</li>
          <li onClick={() => handleNavigation('scan')}>Scan Product</li>
          <li onClick={() => handleNavigation('history')}>Scan History</li>
        </ul>
      </div>
    </nav>
  );
}

export default Navigation;