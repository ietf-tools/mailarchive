from abc import ABC, abstractmethod

class BaseSearchBackend(ABC):
    @abstractmethod
    def setup(self):
        """One time setup of index and schema"""
        pass

    @abstractmethod
    def update(self, document: dict) -> None:
        """Put a document in the search index"""
        pass

    @abstractmethod
    def remove(self, id: str) -> None:
        """Remove a document from the search index"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Empty the search index"""
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 10, **kwargs) -> list:
        """Executes a search of the index"""
        pass