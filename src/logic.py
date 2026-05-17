# logic.py - Business logic for the Qt5 Project Offline app
#
# This module manages the in-memory representation of project data and provides
# methods for manipulating and accessing project information.

# Logic module for the Qt5 Project Offline app
class ProjectLogic:
    def __init__(self):
        self.project_data = None

    def load_data(self, data):
        self.project_data = data

    def get_data(self):
        return self.project_data

    # Add more business logic methods as needed
