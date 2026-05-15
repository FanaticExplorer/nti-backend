"""
Routers package for the NTI backend application.

Contains all API route definitions organized by domain:
- admin: Dashboard statistics, audit log, CSV exports
- applications: Application lifecycle management (CRUD, submission, status transitions)
- auth: Authentication and authorization (register, login, token refresh, password reset)
- calls: Call for proposals management
- content: CMS content pages and news articles
- documents: Document upload/download for applications
- evaluations: Evaluator scoring and recommendations
- mentorships: Mentor assignments and mentorship logs
- milestones: Application milestone tracking
- organizations: Partner organization management
- programs: Program type definitions
- student_profiles: Student profile management
- teams: Team creation and member management
- users: User administration (listing, role changes, deactivation)
"""
