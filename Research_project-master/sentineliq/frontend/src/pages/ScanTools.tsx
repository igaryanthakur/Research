import React from 'react';
import ScanToolsView from '../components/dashboard/ScanToolsView';

const ScanToolsPage: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col min-h-0">
      <ScanToolsView />
    </div>
  );
};

export default ScanToolsPage;
