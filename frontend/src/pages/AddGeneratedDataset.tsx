import { Navigate, useParams } from 'react-router-dom';

export const AddGeneratedDataset = () => {
  const { generatedId = '' } = useParams();
  return <Navigate to={`/upload?generatedId=${encodeURIComponent(generatedId)}`} replace />;
};
