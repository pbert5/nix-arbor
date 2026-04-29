from flask import Blueprint, current_app, request, jsonify
from backend.utils.responses import success_response, error_response
from backend.auth import require_role
from backend.database import Database
from backend.smb_client import SMBClient
from backend.sources.rclone_source import RcloneSource
import json
import logging
import os

sources_bp = Blueprint('sources', __name__)
logger = logging.getLogger(__name__)

def get_db():
    return current_app.db

@sources_bp.route('/api/sources', methods=['GET'])
@require_role('viewer')
def get_sources():
    """List all configured sources."""
    try:
        source_manager = getattr(current_app, 'source_manager', None)
        if not source_manager:
            return error_response(
                "Source manager unavailable",
                code="sources_unavailable",
                status_code=503,
                detail=getattr(current_app, 'source_manager_unavailable_reason', None),
            )
        
        sources = source_manager.list_sources()
        # Ensure consistency with frontend expectation
        for s in sources:
            s['name'] = s.get('display_name', s.get('id', ''))
            s['type'] = s.get('source_type', '')
            # Reconstruct config object for frontend
            s['config'] = {
                'path': s.get('source_path', ''),
                'username': s.get('username', ''),
                'domain': s.get('domain', ''),
                'nfs_server': s.get('nfs_server', ''),
                'nfs_export': s.get('nfs_export', ''),
                'bucket': s.get('s3_bucket', ''),
                'region': s.get('s3_region', '')
            }
        return success_response(data={'sources': sources})
    except Exception as e:
        logger.error(f"Failed to list sources: {e}")
        return error_response("Failed to retrieve sources list")

@sources_bp.route('/api/sources', methods=['POST'])
@require_role('admin')
def create_source():
    """Create a new source configuration."""
    data = request.get_json() or {}
    name = data.get('name')
    source_type = data.get('type')
    config = data.get('config', {})

    if not name or not source_type:
        return error_response("Name and type are required", status_code=400)

    # Validate connection before saving
    if os.environ.get("FOSSILSAFE_SKIP_SOURCE_TEST") == "1":
        pass
    elif source_type == 'smb':
        smb = SMBClient()
        success = smb.connect(
            config.get('path'),
            config.get('username'),
            config.get('password'),
            config.get('domain')
        )
        if not success:
            return error_response("Failed to connect to SMB share", status_code=400)

    elif source_type in ['s3', 'b2']:
        success, message = RcloneSource.test_connection_with_credentials(source_type, config)
        if not success:
            return error_response(f"Failed to validate {source_type.upper()} connection: {message}", status_code=400)

    elif source_type == 'nfs':
        from backend.sources.nfs_source import NFSSource
        res = NFSSource.test_connection(config.get('nfs_server'), config.get('nfs_export'))
        if not res['ok']:
             return error_response(f"Failed to validate NFS connection: {res['detail']}", status_code=400)

    elif source_type == 'ssh':
        from backend.sources.ssh_source import SSHSource
        success, message = SSHSource.test_connection(
            config.get('host'),
            config.get('username'),
            int(config.get('port', 22))
        )
        if not success:
            return error_response(message, status_code=400)

    elif source_type == 'rsync':
        from backend.sources.rsync_source import RsyncSource
        success, message = RsyncSource.test_connection(
            config.get('host'),
            config.get('username'),
            int(config.get('port', 22))
        )
        if not success:
            return error_response(message, status_code=400)

    try:
        source_manager = getattr(current_app, 'source_manager', None)
        if not source_manager:
            return error_response(
                "Source manager unavailable",
                code="sources_unavailable",
                status_code=503,
                detail=getattr(current_app, 'source_manager_unavailable_reason', None),
            )

        # Map to Database schema
        source_id = data.get('source_id') or name.lower().replace(' ', '_')
        payload = {
            'id': source_id,
            'source_type': source_type,
            'source_path': config.get('path', ''),
            'display_name': name,
            'username': config.get('username', ''),
            'password': config.get('password', ''),
            'domain': config.get('domain', ''),
            'nfs_server': config.get('nfs_server', ''),
            'nfs_export': config.get('nfs_export', ''),
            's3_bucket': config.get('bucket', ''),
            's3_region': config.get('region', ''),
            'host': config.get('host', ''),
            'port': config.get('port', 22)
        }
        
        source_manager.store_source(payload)
        return success_response(message="Source created successfully", data={'source_id': source_id})
    except Exception as e:
        logger.exception("Failed to create source")
        # Do not return str(e) as it may contain credentials from the payload
        return error_response("Failed to create source configuration. Check logs for details.")

@sources_bp.route('/api/sources/<source_id>', methods=['DELETE'])
@require_role('admin')
def delete_source(source_id: str):
    """Delete a source configuration."""
    try:
        db = get_db()
        db.delete_source(source_id)
        return success_response(message="Source deleted")
    except Exception as e:
        logger.error(f"Failed to delete source {source_id}: {e}")
        return error_response("Failed to delete source")

@sources_bp.route('/api/sources/test', methods=['POST'])
@require_role('admin')
def test_source_connection():
    """Test connection for a source configuration (unsaved)."""
    data = request.get_json(silent=True) or {}
    source_type = str(data.get('type') or data.get('source_type') or '').strip().lower()
    config = data.get('config') if isinstance(data.get('config'), dict) else {
        'path': data.get('source_path') or data.get('path') or '',
        'username': data.get('username') or '',
        'password': data.get('password') or '',
        'domain': data.get('domain') or '',
        'nfs_server': data.get('nfs_server') or '',
        'nfs_export': data.get('nfs_export') or '',
        'host': data.get('host') or data.get('rsync_host') or '',
        'username_or_user': data.get('username') or data.get('user') or data.get('rsync_user') or '',
        'port': data.get('port') or data.get('rsync_port') or 22,
        'bucket': data.get('bucket') or data.get('s3_bucket') or '',
        'region': data.get('region') or data.get('s3_region') or '',
    }

    status_map = {
        'invalid_request': 400,
        'auth_failed': 401,
        'share_not_found': 404,
        'host_unreachable': 502,
        'connection_failed': 502,
        'smb_unavailable': 503,
        'service_unavailable': 503,
        'smb_tool_missing': 503,
        'timeout': 504,
    }

    if not source_type:
        return error_response("source_type is required", code="invalid_request", status_code=400)

    if source_type == 'smb':
        source_path = config.get('path') or ''
        if not source_path:
            return error_response("source_path is required", code="invalid_request", status_code=400)

        smb = getattr(current_app, 'smb_client', None)
        if smb is None:
            detail = getattr(current_app, 'smb_unavailable_reason', None)
            return error_response(
                "SMB client unavailable",
                code="smb_unavailable",
                status_code=503,
                detail=detail,
            )

        username = config.get('username') or config.get('username_or_user') or ''
        password = config.get('password') or ''
        domain = config.get('domain') or ''
        res = smb.test_connection_detailed(source_path, username, password, domain)
        if res['ok']:
            return success_response(message="Connection successful")
        return error_response(
            res['message'],
            code=res.get('error_code', 'connection_failed'),
            detail=res.get('detail'),
            status_code=status_map.get(res.get('error_code'), 502),
        )
            
    elif source_type in ['s3', 'b2']:
        success, message = RcloneSource.test_connection_with_credentials(source_type, config)
        if success:
            return success_response(message="Connection successful")
        else:
            return error_response(f"Connection failed: {message}")

    elif source_type == 'nfs':
        from backend.sources.nfs_source import NFSSource
        res = NFSSource.test_connection(config.get('nfs_server'), config.get('nfs_export'))
        if res['ok']:
            return success_response(message="Connection successful")
        else:
            return error_response(res['detail'])

    elif source_type == 'ssh':
        from backend.sources.ssh_source import SSHSource
        success, message = SSHSource.test_connection(
            config.get('host'),
            config.get('username') or config.get('username_or_user'),
            int(config.get('port', 22))
        )
        if success:
            return success_response(message="Connection successful")
        else:
            return error_response(message)

    elif source_type == 'rsync':
        from backend.sources.rsync_source import RsyncSource
        success, message = RsyncSource.test_connection(
            config.get('host'),
            config.get('username') or config.get('username_or_user'),
            int(config.get('port', 22))
        )
        if success:
            return success_response(message="Connection successful")
        else:
            return error_response(message)

    return error_response("Unsupported source type", code="invalid_request", status_code=400)
