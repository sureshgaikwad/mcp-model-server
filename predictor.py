# src/predictor.py
import kserve
import logging
import asyncio
from typing import Dict, Any
from model.model import MCPDeploymentModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MCPModelPredictor(kserve.Model):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name
        self.model = None
        self.ready = False

    def load(self) -> bool:
        """Load the MCP deployment model"""
        try:
            logger.info("Loading MCP Deployment Model...")
            self.model = MCPDeploymentModel()
            self.ready = True
            logger.info("MCP Deployment Model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    async def predict(self, payload: Dict, headers: Dict[str, str] = None) -> Dict[str, Any]:
        """Predict method called by KServe"""
        try:
            logger.info(f"Received prediction request: {payload}")
            
            # Extract instances from payload
            instances = payload.get("instances", [])
            if not instances:
                return {"error": "No instances provided"}
            
            # Process each instance
            predictions = []
            for instance in instances:
                prediction = await self.model.predict(instance)
                predictions.append(prediction)
            
            return {"predictions": predictions}
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return {"error": str(e)}

    def ready(self) -> bool:
        """Health check endpoint"""
        return self.ready

if __name__ == "__main__":
    model = MCPModelPredictor("mcp-deployment")
    model.load()
    kserve.ModelServer().start([model])
