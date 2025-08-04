import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ModelResult:
    """Data class representing a single model's execution result"""
    unique_id: str
    model_name: str
    status: str
    is_success: bool
    total_time: float
    compile_time: float
    execute_time: float
    other_time: float
    rows_affected: int
    thread_id: Optional[str]
    message: str
    error_message: Optional[str]
    timing_details: List[Dict[str, Any]]


class DbtRunResultsParser:
    """Parser for dbt run_results.json files"""
    
    def __init__(self):
        pass
    
    def parse_run_results(self, run_results: Dict[str, Any]) -> List[ModelResult]:
        """
        Parse dbt run_results.json and extract model execution information
        
        Args:
            run_results: The parsed run_results.json dictionary
            
        Returns:
            List of ModelResult objects
            
        Raises:
            ValueError: If run_results format is invalid
        """
        if not run_results or 'results' not in run_results:
            raise ValueError('Invalid run_results.json format - missing results array')
        
        return [self._parse_single_result(result) for result in run_results['results']]
    
    def _parse_single_result(self, result: Dict[str, Any]) -> ModelResult:
        """Parse a single result entry"""
        # Extract timing information
        timing_breakdown = self._extract_timing(result.get('timing', []))
        
        # Extract rows affected from adapter response
        rows_affected = self._extract_rows_affected(result.get('adapter_response'))
        
        # Determine success status
        is_success = result.get('status') == 'success'
        
        return ModelResult(
            # Model identification
            unique_id=result.get('unique_id', 'unknown'),
            model_name=self._extract_model_name(result.get('unique_id')),
            
            # Execution status
            status=result.get('status', 'unknown'),
            is_success=is_success,
            
            # Timing information (in seconds)
            total_time=result.get('execution_time', 0.0),
            compile_time=timing_breakdown.get('compile', 0.0),
            execute_time=timing_breakdown.get('execute', 0.0),
            other_time=timing_breakdown.get('other', 0.0),
            
            # Database impact
            rows_affected=rows_affected,
            
            # Additional metadata
            thread_id=result.get('thread_id'),
            message=result.get('message', ''),
            error_message=result.get('message') if not is_success else None,
            
            # Raw timing data for reference
            timing_details=result.get('timing', [])
        )
    
    def _extract_timing(self, timing: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Extract timing breakdown from timing array
        
        Args:
            timing: Array of timing objects
            
        Returns:
            Dictionary with timing breakdown by stage
        """
        breakdown = {
            'compile': 0.0,
            'execute': 0.0,
            'other': 0.0
        }
        
        for stage in timing:
            duration = stage.get('duration', 0.0)
            name = (stage.get('name', '')).lower()
            
            if 'compile' in name:
                breakdown['compile'] += duration
            elif 'execute' in name:
                breakdown['execute'] += duration
            else:
                breakdown['other'] += duration
        
        return breakdown
    
    def _extract_rows_affected(self, adapter_response: Optional[Dict[str, Any]]) -> int:
        """
        Extract rows affected from adapter response
        
        Args:
            adapter_response: Adapter response object
            
        Returns:
            Number of rows affected
        """
        if not adapter_response:
            return 0
        
        # Try different possible fields for rows affected
        return (adapter_response.get('rows_affected') or 
                adapter_response.get('rowsAffected') or 
                adapter_response.get('row_count') or 
                adapter_response.get('rowCount') or 
                0)
    
    def _extract_model_name(self, unique_id: Optional[str]) -> str:
        """
        Extract model name from unique_id
        
        Args:
            unique_id: dbt unique identifier
            
        Returns:
            Model name
        """
        if not unique_id:
            return 'unknown'
        
        # Format: model.package_name.model_name
        parts = unique_id.split('.')
        return parts[2] if len(parts) >= 3 else unique_id
    
    def filter_by_status(self, results: List[ModelResult], status: str) -> List[ModelResult]:
        """
        Filter results by status
        
        Args:
            results: List of ModelResult objects
            status: Status to filter by ('success', 'error', 'skipped')
            
        Returns:
            Filtered list of ModelResult objects
        """
        return [result for result in results if result.status == status]
    
    def get_summary_stats(self, results: List[ModelResult]) -> Dict[str, Any]:
        """
        Get summary statistics
        
        Args:
            results: List of ModelResult objects
            
        Returns:
            Dictionary with summary statistics
        """
        total_models = len(results)
        successful = sum(1 for r in results if r.is_success)
        failed = sum(1 for r in results if r.status == 'error')
        skipped = sum(1 for r in results if r.status == 'skipped')
        
        total_time = sum(r.total_time for r in results)
        total_rows = sum(r.rows_affected for r in results)
        
        success_rate = (successful / total_models * 100) if total_models > 0 else 0
        
        return {
            'total_models': total_models,
            'successful': successful,
            'failed': failed,
            'skipped': skipped,
            'success_rate': f"{success_rate:.1f}%",
            'total_execution_time': f"{total_time:.2f}s",
            'total_rows_affected': f"{total_rows:,}"
        }
    
    def parse_from_file(self, file_path: str) -> List[ModelResult]:
        """
        Parse run_results.json directly from file
        
        Args:
            file_path: Path to run_results.json file
            
        Returns:
            List of ModelResult objects
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            run_results = json.load(f)
        
        return self.parse_run_results(run_results)
    
    def to_dict_list(self, results: List[ModelResult]) -> List[Dict[str, Any]]:
        """
        Convert ModelResult objects to list of dictionaries
        
        Args:
            results: List of ModelResult objects
            
        Returns:
            List of dictionaries
        """
        return [
            {
                'unique_id': result.unique_id,
                'model_name': result.model_name,
                'status': result.status,
                'is_success': result.is_success,
                'total_time': result.total_time,
                'compile_time': result.compile_time,
                'execute_time': result.execute_time,
                'other_time': result.other_time,
                'rows_affected': result.rows_affected,
                'thread_id': result.thread_id,
                'message': result.message,
                'error_message': result.error_message
            }
            for result in results
        ]


# Example usage and convenience functions
def parse_dbt_run_results(run_results: Dict[str, Any]) -> List[ModelResult]:
    """Convenience function to parse run results"""
    parser = DbtRunResultsParser()
    return parser.parse_run_results(run_results)


def parse_dbt_run_results_from_file(file_path: str) -> List[ModelResult]:
    """Convenience function to parse run results from file"""
    parser = DbtRunResultsParser()
    return parser.parse_from_file(file_path)


if __name__ == "__main__":
    # Example usage
    parser = DbtRunResultsParser()
    
    # Parse from file
    # model_results = parser.parse_from_file('run_results.json')
    
    # Or parse from already loaded JSON
    # with open('run_results.json', 'r') as f:
    #     run_results = json.load(f)
    # model_results = parser.parse_run_results(run_results)
    
    # Get failed models
    # failed_models = parser.filter_by_status(model_results, 'error')
    
    # Get summary statistics
    # summary = parser.get_summary_stats(model_results)
    
    # Convert to dictionary format
    # dict_results = parser.to_dict_list(model_results)
    
    # print("Summary:", summary)
    # print("Failed models:", len(failed_models))
    
    print("DBT Run Results Parser ready to use!")
    print("\nExample usage:")
    print("parser = DbtRunResultsParser()")
    print("results = parser.parse_from_file('run_results.json')")
    print("summary = parser.get_summary_stats(results)")
    print("failed = parser.filter_by_status(results, 'error')")
