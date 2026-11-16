import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { Button, Card, PageHeader } from '../components/ui';

export const NotFound = () => (
  <>
    <PageHeader
      title="Page not found"
      description="The requested route does not exist in the MedDataHub demo."
      actions={
        <Link to="/">
          <Button icon={<Compass size={16} />}>Return to dashboard</Button>
        </Link>
      }
    />
    <Card>
      <div className="empty-state">
        <div className="empty-icon"><Compass size={20} /></div>
        <h3>404 · Route unavailable</h3>
        <p>Check the address or use the sidebar to navigate to a working page.</p>
      </div>
    </Card>
  </>
);
